"""CLI entrypoint and cycle execution daemon for GitHub Issue Monitor."""

from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import html
import logging
import os
import signal
import sys
import time
from pathlib import Path
import aiohttp

from github_issue_monitor.config import MonitorConfig, load_config
from github_issue_monitor.filter import FilterRules, classify_issue
from github_issue_monitor.fetcher import GitHubIssueFetcher, FetchResult, RateLimited, FetchError
from github_issue_monitor.models import parse_issue
from github_issue_monitor.notifier import TelegramIssueNotifier, format_telegram_issue_message
from github_issue_monitor.ste100 import generate_ste100_reply
from github_issue_monitor.storage import IssueStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("github_issue_monitor")


def _is_too_old(created_at_str: str, max_age_hours: int) -> bool:
    """Check if issue created_at timestamp is older than max_age_hours."""
    if not created_at_str or max_age_hours <= 0:
        return False
    try:
        # Standard ISO 8601 parsing (e.g. 2026-11-15T00:00:00Z)
        created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        return created_dt < cutoff
    except Exception:
        return False


async def run_cycle(
    config: MonitorConfig,
    storage: IssueStorage,
    fetcher: GitHubIssueFetcher,
    notifier: TelegramIssueNotifier,
    dry_run: bool = False,
) -> int:
    """Execute a single polling cycle across all configured repositories.

    Returns:
        total_alerts: Total count of alerts delivered (or printed in dry-run).
    """
    filter_rules = FilterRules(
        ignore_users=config.ignore_users,
        keywords=config.keywords,
        bug_labels=config.bug_labels,
        enhancement_labels=config.enhancement_labels,
        help_wanted_labels=config.help_wanted_labels,
    )

    total_alerts = 0

    for repo in config.repos:
        repo_clean = repo.strip()
        etag = storage.get_etag(repo_clean) if not dry_run else None

        try:
            fetch_result = await fetcher.fetch(repo_clean, etag=etag)
        except RateLimited as exc:
            logger.error("GitHub rate limit hit for %s. Reset at %s. Aborting cycle.", repo_clean, exc.reset_at)
            return total_alerts
        except FetchError as exc:
            logger.error("Failed to fetch %s: %s. Continuing to next repository.", repo_clean, exc)
            continue

        if fetch_result.status == "not_modified":
            logger.info("304 Not Modified for repository %s", repo_clean)
            continue

        # Sort issues from oldest to newest by issue number
        raw_issues = sorted(
            fetch_result.issues,
            key=lambda x: int(x.get("number", 0)),
        )

        # Baseline run check
        if not storage.is_baselined(repo_clean):
            if not dry_run:
                for issue in raw_issues:
                    num = int(issue.get("number", 0))
                    title = str(issue.get("title", ""))
                    storage.mark_seen(repo_clean, num, title)
                storage.set_baselined(repo_clean)
                if fetch_result.etag:
                    storage.save_etag(repo_clean, fetch_result.etag)
                logger.info(
                    "Baselined repository %s with %d existing open issues (0 alerts sent).",
                    repo_clean,
                    len(raw_issues),
                )
            else:
                logger.info(
                    "[DRY-RUN] Would baseline repository %s with %d existing open issues.",
                    repo_clean,
                    len(raw_issues),
                )
            continue

        # Normal processing cycle
        repo_alerts = 0
        all_sends_succeeded = True
        overflow_notified = False

        for raw in raw_issues:
            num = int(raw.get("number", 0))
            if not dry_run and storage.is_seen(repo_clean, num):
                continue

            created_at = str(raw.get("created_at", ""))
            if _is_too_old(created_at, config.max_age_hours):
                continue

            is_rel, cat, reason = classify_issue(raw, filter_rules)
            if not is_rel or cat is None:
                # Do NOT mark seen: re-evaluate in future cycles if labels/state changes
                continue

            # Check alert limit per cycle
            if repo_alerts >= config.max_alerts_per_cycle:
                if not overflow_notified and not dry_run:
                    overflow_msg = (
                        f"⚠️ <b>{html.escape(repo_clean)}</b>: More than {config.max_alerts_per_cycle} "
                        f"relevant issues found in this cycle. Capped alerting."
                    )
                    await notifier.send_message(overflow_msg)
                    overflow_notified = True
                break

            issue_data = parse_issue(raw, repo_clean)
            reply = generate_ste100_reply(issue_data, cat)

            if dry_run:
                msg = format_telegram_issue_message(issue_data, reply)
                print(f"\n--- [DRY-RUN ALERT: {repo_clean} #{num}] ---\n{msg}\n")
                repo_alerts += 1
            else:
                ok = await notifier.send_issue(issue_data, reply)
                if ok:
                    storage.mark_seen(repo_clean, num, issue_data.title)
                    repo_alerts += 1
                else:
                    all_sends_succeeded = False
                    logger.error("Failed to deliver alert for %s #%d", repo_clean, num)

        if not dry_run and all_sends_succeeded and fetch_result.etag:
            storage.save_etag(repo_clean, fetch_result.etag)

        total_alerts += repo_alerts

    return total_alerts


class SingleInstanceLock:
    """Ensure only one instance runs simultaneously using an OS file lock."""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fd = None

    def acquire(self) -> bool:
        import fcntl
        Path(self.lock_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = open(self.lock_path, "w")
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd.write(f"{os.getpid()}\n")
            self._fd.flush()
            return True
        except (IOError, OSError):
            return False

    def release(self) -> None:
        import fcntl
        if self._fd:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                self._fd.close()
            except Exception:
                pass


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    storage = IssueStorage(config.db_path)

    lock_file = str(Path(config.db_path).parent / "monitor.lock")
    lock = SingleInstanceLock(lock_file)
    if not lock.acquire():
        logger.error("Another instance of github_issue_monitor is already running (lock held at %s). Exiting.", lock_file)
        sys.exit(1)

    stop_event = asyncio.Event()

    def _handle_signal(sig_name: str):
        logger.info("Received signal %s. Shutting down gracefully...", sig_name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, lambda s=s: _handle_signal(signal.Signals(s).name))
        except NotImplementedError:
            pass

    async with aiohttp.ClientSession() as session:
        fetcher = GitHubIssueFetcher(session=session, token=config.github_token)
        notifier = TelegramIssueNotifier(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            session=session,
        )

        try:
            if args.once:
                logger.info("Executing single cycle (--once, dry_run=%s)...", args.dry_run)
                alerts = await run_cycle(config, storage, fetcher, notifier, dry_run=args.dry_run)
                logger.info("Cycle complete. Total alerts processed: %d", alerts)
                return

            logger.info(
                "Starting GitHub Issue Monitor daemon (interval: %d min, repos: %s)...",
                config.interval_minutes,
                config.repos,
            )

            while not stop_event.is_set():
                start_time = time.monotonic()
                try:
                    alerts = await run_cycle(config, storage, fetcher, notifier, dry_run=args.dry_run)
                    logger.info("Cycle finished. %d alert(s) sent.", alerts)
                except Exception as exc:
                    logger.exception("Unexpected error during monitoring cycle: %s", exc)

                elapsed = time.monotonic() - start_time
                sleep_target = max(5.0, config.interval_minutes * 60.0 - elapsed)

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=sleep_target)
                except asyncio.TimeoutError:
                    pass

        finally:
            lock.release()
            storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Issue Monitor")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without sending notifications or updating DB")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")

    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting.")


if __name__ == "__main__":
    main()
