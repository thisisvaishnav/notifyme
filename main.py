"""Main application entry point, scheduler loop, and engine coordinator."""

from __future__ import annotations
import os
import sys
import time
import random
import signal
import logging
from logging.handlers import RotatingFileHandler
import asyncio
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any

from config import AppConfig, load_config
from storage import SQLiteStorage
from filters import FilterEngine, TweetData
from notifier import TelegramNotifier
from fetcher import (
    BaseFetcher,
    TwikitFetcher,
    RateLimitException,
    SessionExpiredException,
    AccountLockedException,
    AccountSuspendedException,
    NetworkException,
    FetcherException,
)
from follower_tracker import FollowerTrackerEngine, calculate_prep_start_time
from web import WebDashboard


def setup_logging(log_dir: str = "data") -> logging.Logger:
    """Set up structured logging to stdout and rotating log file without leaking secrets."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(log_dir, "monitor.log")

    logger = logging.getLogger("notifyme")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Console Handler
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setLevel(logging.INFO)
    c_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)

    # Rotating File Handler (10MB per file, max 3 files)
    f_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    f_handler.setLevel(logging.INFO)
    f_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    f_handler.setFormatter(f_format)
    logger.addHandler(f_handler)

    return logger


class BackoffManager:
    """Calculates exponential backoff delays with jitter upon polling failures."""

    def __init__(
        self,
        initial_seconds: int = 60,
        max_seconds: int = 900,
        factor: float = 2.0,
        jitter_max_seconds: int = 10,
    ):
        self.initial_seconds = initial_seconds
        self.max_seconds = max_seconds
        self.factor = factor
        self.jitter_max_seconds = jitter_max_seconds
        self.failure_count = 0

    def record_failure(self) -> None:
        """Increment failure streak."""
        self.failure_count += 1

    def record_success(self) -> None:
        """Reset failure counter on success."""
        self.failure_count = 0

    def next_delay(self, apply_jitter: bool = True) -> float:
        """Compute the duration to wait before the next attempt."""
        base = min(
            self.initial_seconds * (self.factor ** self.failure_count),
            self.max_seconds,
        )
        jitter = random.uniform(0, self.jitter_max_seconds) if apply_jitter else 0.0
        return base + jitter


class MonitorEngine:
    """Core monitor engine driving the poll loop, deduplication, filtering, and alerts."""

    def __init__(
        self,
        config: AppConfig,
        storage: SQLiteStorage,
        fetcher: BaseFetcher,
        notifier: TelegramNotifier,
    ):
        self.config = config
        self.storage = storage
        self.fetcher = fetcher
        self.notifier = notifier
        self.filter_engine = FilterEngine(config.filters)

        self.backoff = BackoffManager(
            initial_seconds=config.poll.interval_seconds,
            max_seconds=900,
            factor=2.0,
            jitter_max_seconds=config.poll.jitter_max_seconds,
        )

        self.follower_tracker = FollowerTrackerEngine(
            config=config.follower_tracker,
            storage=storage,
            fetcher_client=getattr(fetcher, "client", None),
            notifier=notifier,
        )

        self.logger = logging.getLogger("notifyme.engine")
        self.is_paused: bool = False
        self.is_running: bool = False
        self.consecutive_failures: int = 0
        self.last_successful_poll: float = time.time()
        self.start_time: float = time.time()
        self._manual_poll_event: asyncio.Event = asyncio.Event()

    def trigger_immediate_poll(self) -> None:
        """Signal the polling loop to awaken immediately."""
        self._manual_poll_event.set()

    async def poll_once(self) -> int:
        """Execute a single polling cycle.

        Returns:
            Number of newly notified tweets.
        """
        list_id = self.config.x_account.list_id
        if not list_id:
            raise FetcherException("No X List ID provided. Please set list_id in config.yaml or X_LIST_ID in .env.")

        self.logger.info("Polling X List timeline (List ID: %s)...", list_id)
        tweets = await self.fetcher.fetch_list_tweets(list_id=list_id, count=40)

        # Baseline Handling on first run
        if not self.storage.is_baseline_set():
            highest_id = max((t.id for t in tweets), default=0)
            self.storage.set_baseline(highest_id)
            self.logger.info(
                "Baseline established silently at tweet ID %s. Found %d existing tweets (notified none).",
                highest_id,
                len(tweets),
            )
            self.storage.record_poll("success", tweets_found=len(tweets), tweets_notified=0)
            self.last_successful_poll = time.time()
            return 0

        last_seen_id = self.storage.get_last_seen_id()
        # Find candidates newer than last seen snowflake ID
        new_candidates = [t for t in tweets if t.id > last_seen_id]

        # Sort chronologically (oldest tweet first)
        new_candidates.sort(key=lambda t: t.id)

        notified_count = 0
        for tweet in new_candidates:
            # Check deduplication in database
            if self.storage.is_tweet_notified(tweet.id):
                self.logger.debug("Tweet %s already notified; skipping.", tweet.id)
                self.storage.update_last_seen_id(tweet.id)
                continue

            # Evaluate filter rules
            allowed, reason = self.filter_engine.should_notify(tweet)
            if not allowed:
                self.logger.info("Filtered tweet %s by @%s: %s", tweet.id, tweet.author_handle, reason)
                self.storage.update_last_seen_id(tweet.id)
                continue

            # Deliver to Telegram
            self.logger.info("Delivering new post %s by @%s to Telegram...", tweet.id, tweet.author_handle)
            sent = await self.notifier.send_tweet_notification(tweet)
            if sent:
                self.storage.mark_tweet_notified(
                    tweet_id=tweet.id,
                    author_handle=tweet.author_handle,
                    text=tweet.text,
                    created_at=tweet.created_at,
                    media_urls=tweet.media,
                )
                notified_count += 1
                # Small pause to be gentle with Telegram API rate limits
                await asyncio.sleep(0.5)

            self.storage.update_last_seen_id(tweet.id)

        self.storage.record_poll("success", tweets_found=len(tweets), tweets_notified=notified_count)
        self.last_successful_poll = time.time()
        self.logger.info("Cycle finished: %d new tweets found, %d notified.", len(new_candidates), notified_count)
        return notified_count

    async def _handle_poll_error(self, exc: Exception) -> None:
        """Process poll errors, log clearly, increment backoff, and dispatch alerts."""
        self.consecutive_failures += 1
        self.backoff.record_failure()
        err_msg = str(exc)

        if isinstance(exc, RateLimitException):
            self.logger.warning("X Rate Limit hit (HTTP 429). Exponential backoff active: %s", err_msg)
        elif isinstance(exc, SessionExpiredException):
            self.logger.error("X Session expired or unauthorized: %s", err_msg)
            await self.notifier.send_alert("session_expired", f"X account session is invalid: {err_msg}")
        elif isinstance(exc, AccountLockedException):
            self.logger.error("X Data Account locked or captcha challenge triggered: %s", err_msg)
            await self.notifier.send_alert("account_locked", f"X data account is locked/challenged: {err_msg}")
        elif isinstance(exc, AccountSuspendedException):
            self.logger.critical("X Data Account suspended: %s", err_msg)
            await self.notifier.send_alert("account_suspended", "X data account has been suspended.")
        elif isinstance(exc, NetworkException):
            self.logger.warning("Network failure reaching X: %s", err_msg)
        else:
            self.logger.error("Unexpected error during poll cycle: %s", err_msg, exc_info=True)

        self.storage.record_poll("error", error_message=err_msg)

        if self.consecutive_failures >= self.config.alerts.max_consecutive_failures:
            await self.notifier.send_alert(
                "consecutive_failures",
                f"Polling has failed {self.consecutive_failures} consecutive times. Last error: {err_msg}",
            )

    async def run_follower_tracker_loop(self) -> None:
        """Run daily safe-pacing follower tracking loop."""
        if not self.config.follower_tracker.enabled:
            return

        self.logger.info(
            "Follower tracker active for @%s (Target digest: %s, Lead time: %dm)",
            self.config.follower_tracker.target_handle,
            self.config.follower_tracker.schedule_time,
            self.config.follower_tracker.prep_lead_minutes,
        )

        while self.is_running:
            try:
                sched_parts = self.config.follower_tracker.schedule_time.split(":")
                target_hour = int(sched_parts[0])
                target_min = int(sched_parts[1]) if len(sched_parts) > 1 else 0
                target_time = dtime(target_hour, target_min)

                prep_time = calculate_prep_start_time(
                    target_time,
                    lead_minutes=self.config.follower_tracker.prep_lead_minutes,
                )

                now = datetime.now()
                next_run = datetime.combine(now.date(), prep_time)
                if next_run <= now:
                    next_run += timedelta(days=1)

                seconds_until_run = (next_run - now).total_seconds()
                self.logger.info(
                    "Next follower audit scheduled at %s (in %.1f hours)",
                    next_run.strftime("%Y-%m-%d %H:%M:%S"),
                    seconds_until_run / 3600,
                )

                await asyncio.sleep(seconds_until_run)
                if not self.is_running:
                    break

                self.logger.info("Triggering scheduled daily follower audit...")
                if not self.follower_tracker.fetcher_client and hasattr(self.fetcher, "client"):
                    self.follower_tracker.fetcher_client = self.fetcher.client

                await self.follower_tracker.run_audit(send_digest_now=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in follower tracker loop: %s", e, exc_info=True)
                await asyncio.sleep(300)

    async def run_loop(self) -> None:
        """Continuous polling loop respecting interval, jitter, and backoff."""
        self.is_running = True
        self.logger.info("Starting monitoring loop...")

        # Initialize fetcher session
        try:
            await self.fetcher.initialize()
            if hasattr(self.fetcher, "client"):
                self.follower_tracker.fetcher_client = self.fetcher.client
        except Exception as exc:
            self.logger.critical("Failed to initialize fetcher: %s", exc, exc_info=True)
            await self.notifier.send_alert("init_failed", f"Failed to initialize X fetcher: {exc}")
            return

        while self.is_running:
            if self.is_paused:
                self.logger.debug("Monitor is paused. Sleeping...")
                await asyncio.sleep(2)
                continue

            try:
                prev_streak = self.consecutive_failures
                await self.poll_once()

                # If we just recovered from failures, send recovery notice
                if prev_streak >= self.config.alerts.max_consecutive_failures:
                    await self.notifier.send_recovery_alert(
                        "consecutive_failures",
                        f"Polling recovered after {prev_streak} failures.",
                    )
                    await self.notifier.send_recovery_alert(
                        "session_expired",
                        "X session re-authenticated successfully.",
                    )
                    self.consecutive_failures = 0
                    self.backoff.record_success()

                # Normal sleep with jitter
                delay = self.config.poll.interval_seconds + random.uniform(
                    0, self.config.poll.jitter_max_seconds
                )
            except Exception as exc:
                await self._handle_poll_error(exc)
                delay = self.backoff.next_delay(apply_jitter=True)
                self.logger.info("Backing off for %.1f seconds before retry...", delay)

            # Wait for either delay completion or immediate manual trigger
            self._manual_poll_event.clear()
            try:
                await asyncio.wait_for(self._manual_poll_event.wait(), timeout=delay)
                self.logger.info("Manual poll signal received; resuming cycle immediately.")
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

        self.logger.info("Monitor loop stopped.")


async def main() -> None:
    """Bootstrap application components, web dashboard, and handle termination signals."""
    logger = setup_logging()
    logger.info("Bootstrapping X Account Monitor...")

    config = load_config()
    storage = SQLiteStorage(config.storage.db_path)
    storage.initialize()

    fetcher = TwikitFetcher(config.x_account)
    notifier = TelegramNotifier(config.telegram, config.alerts)
    engine = MonitorEngine(config, storage, fetcher, notifier)

    web_server: WebDashboard | None = None
    if config.web.enabled:
        web_server = WebDashboard(engine, host=config.web.host, port=config.web.port)
        try:
            await web_server.start()
        except OSError as exc:
            if exc.errno == 48:
                logger.error(
                    "Port %s is already in use! An instance of NotifyMe is already running in the background. "
                    "Run 'pkill -f \"python main.py\"' to stop it, or check your running services.",
                    config.web.port,
                )
                await notifier.close()
                await fetcher.close()
                return
            raise

    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received termination signal. Shutting down gracefully...")
        engine.is_running = False
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    # Run monitor task and optional follower tracker task
    tasks = [asyncio.create_task(engine.run_loop())]
    if config.follower_tracker.enabled:
        tasks.append(asyncio.create_task(engine.run_follower_tracker_loop()))

    # Wait until shutdown signaled
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        engine.is_running = False
        for t in tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        if web_server:
            await web_server.stop()
        await notifier.close()
        await fetcher.close()
        logger.info("All services shut down cleanly. Goodbye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
