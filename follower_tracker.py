"""Daily Follower & Unfollower Tracking Engine for NotifyMe."""

from __future__ import annotations
import asyncio
import random
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import FollowerTrackerConfig
    from storage import SQLiteStorage
    from notifier import TelegramNotifier

logger = logging.getLogger("notifyme.follower_tracker")


def calculate_prep_start_time(target_schedule_time: time, lead_minutes: int = 40) -> time:
    """Calculate the time to begin scraping in advance so the report delivers on time.

    Args:
        target_schedule_time: Target time for delivery (e.g. 09:00).
        lead_minutes: Number of minutes prior to start scraping (e.g. 40).

    Returns:
        The time object when scraping should begin (e.g. 08:20).
    """
    dummy_date = datetime(2026, 1, 2, target_schedule_time.hour, target_schedule_time.minute, target_schedule_time.second)
    prep_datetime = dummy_date - timedelta(minutes=lead_minutes)
    return prep_datetime.time()


@dataclass
class FollowerUser:
    """Individual user account representation."""
    id: int
    screen_name: str
    name: str = ""


@dataclass
class FollowerDiff:
    """Calculated difference between two follower/following states."""
    target_handle: str
    total_followers: int
    total_following: int
    net_follower_change: int
    new_followers: list[FollowerUser] = field(default_factory=list)
    unfollowers: list[FollowerUser] = field(default_factory=list)
    mutuals: list[FollowerUser] = field(default_factory=list)
    not_following_back: list[FollowerUser] = field(default_factory=list)
    is_baseline: bool = False


def format_follower_digest(diff: FollowerDiff) -> str:
    """Generate a clean, high-conversion Telegram HTML daily digest."""
    net_str = f"+{diff.net_follower_change}" if diff.net_follower_change > 0 else str(diff.net_follower_change)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 <b>Daily Follower Report for @{diff.target_handle}</b>",
        f"📅 <i>{now_str}</i>",
        "",
        f"👥 Total Followers: <b>{diff.total_followers}</b> ({net_str})",
        f"📡 Total Following: <b>{diff.total_following}</b>",
        f"🤝 Mutual Follows: <b>{len(diff.mutuals)}</b>",
        f"⚠️ Not Following You Back: <b>{len(diff.not_following_back)}</b>",
        "",
    ]

    if diff.is_baseline:
        lines.append("ℹ️ <i>Initial baseline established. Starting tomorrow, daily follower gains and unfollowers will be tracked here.</i>")
        return "\n".join(lines)

    # 1. New Followers Section
    if diff.new_followers:
        lines.append(f"🟢 <b>New Followers ({len(diff.new_followers)}):</b>")
        for u in diff.new_followers[:10]:
            name_part = f" ({u.name})" if u.name else ""
            lines.append(f"• <a href=\"https://x.com/{u.screen_name}\">@{u.screen_name}</a>{name_part}")
        if len(diff.new_followers) > 10:
            lines.append(f"<i>...and {len(diff.new_followers) - 10} more</i>")
        lines.append("")
    else:
        lines.append("🟢 New Followers: <b>None</b>")

    # 2. Unfollowers Section
    if diff.unfollowers:
        lines.append(f"🔴 <b>Unfollowers ({len(diff.unfollowers)}):</b>")
        for u in diff.unfollowers[:15]:
            name_part = f" ({u.name})" if u.name else ""
            lines.append(f"• <a href=\"https://x.com/{u.screen_name}\">@{u.screen_name}</a>{name_part}")
        if len(diff.unfollowers) > 15:
            lines.append(f"<i>...and {len(diff.unfollowers) - 15} more</i>")
        lines.append("")
    else:
        lines.append("🔴 Unfollowers: <b>None</b> (0 accounts unfollowed)")

    # 3. Quick Action Link
    lines.append("")
    lines.append("🌐 <i>Manage & unfollow non-mutuals from your NotifyMe Web Dashboard.</i>")

    return "\n".join(lines)


class FollowerTrackerEngine:
    """Safe, rate-limit conscious engine to fetch, diff, and report daily follower changes."""

    def __init__(
        self,
        config: FollowerTrackerConfig,
        storage: SQLiteStorage,
        fetcher_client: Any = None,
        notifier: TelegramNotifier | None = None,
    ):
        self.config = config
        self.storage = storage
        self.fetcher_client = fetcher_client
        self.notifier = notifier
        self._is_running_audit = False

    @staticmethod
    def compute_diff(
        prev_followers: dict[int, FollowerUser],
        prev_following: dict[int, FollowerUser],
        curr_followers: dict[int, FollowerUser],
        curr_following: dict[int, FollowerUser],
        is_first_run: bool = False,
    ) -> FollowerDiff:
        """Compute the diff between two snapshots."""
        curr_follower_ids = set(curr_followers.keys())
        curr_following_ids = set(curr_following.keys())

        # Mutuals: in both curr_followers and curr_following
        mutual_ids = curr_follower_ids.intersection(curr_following_ids)
        mutuals = [curr_following[uid] for uid in mutual_ids if uid in curr_following]

        # Not following back: people you follow who do not follow you
        not_following_back_ids = curr_following_ids - curr_follower_ids
        not_following_back = [curr_following[uid] for uid in not_following_back_ids if uid in curr_following]

        if is_first_run:
            return FollowerDiff(
                target_handle="",
                total_followers=len(curr_followers),
                total_following=len(curr_following),
                net_follower_change=0,
                new_followers=[],
                unfollowers=[],
                mutuals=mutuals,
                not_following_back=not_following_back,
                is_baseline=True,
            )

        prev_follower_ids = set(prev_followers.keys())

        # New followers: in curr_followers but not prev_followers
        new_ids = curr_follower_ids - prev_follower_ids
        new_followers = [curr_followers[uid] for uid in new_ids]

        # Unfollowers: in prev_followers but not curr_followers
        lost_ids = prev_follower_ids - curr_follower_ids
        unfollowers = [prev_followers[uid] for uid in lost_ids]

        net_change = len(curr_followers) - len(prev_followers)

        return FollowerDiff(
            target_handle="",
            total_followers=len(curr_followers),
            total_following=len(curr_following),
            net_follower_change=net_change,
            new_followers=new_followers,
            unfollowers=unfollowers,
            mutuals=mutuals,
            not_following_back=not_following_back,
            is_baseline=is_first_run,
        )

    async def fetch_user_list_safely(self, fetch_func, user_id: str | int, label: str = "accounts") -> list[FollowerUser]:
        """Fetch all accounts with 10-20s safe pacing between pages, stopping safely at terminal cursor."""
        users_list: list[FollowerUser] = []
        seen_ids: set[int] = set()
        page_num = 1
        logger.info("Starting safe fetch for %s...", label)

        current_page = await fetch_func(user_id, count=70)
        while current_page:
            new_in_page = 0
            for u in current_page:
                uid = int(u.id)
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    new_in_page += 1
                    users_list.append(
                        FollowerUser(
                            id=uid,
                            screen_name=getattr(u, "screen_name", "") or "",
                            name=getattr(u, "name", "") or "",
                        )
                    )

            logger.info("Fetched %s page %d (%d new accounts, %d total collected)", label, page_num, new_in_page, len(users_list))

            cursor = getattr(current_page, "next_cursor", None)
            if not cursor or str(cursor).startswith("0|") or new_in_page == 0:
                logger.info("Reached end of list for %s at page %d (terminal cursor: %s)", label, page_num, cursor)
                break

            if not hasattr(current_page, "next") or not callable(getattr(current_page, "next", None)):
                break

            # Safe browsing sleep between min and max request delays (e.g. 10 to 20s)
            delay = random.uniform(self.config.min_request_delay_seconds, self.config.max_request_delay_seconds)
            logger.info("Safe pacing: sleeping %.1fs before next page of %s...", delay, label)
            await asyncio.sleep(delay)

            try:
                current_page = await current_page.next()
            except Exception as e:
                logger.warning("Reached end or error on page %d of %s: %s", page_num, label, e)
                break
            page_num += 1

        logger.info("Finished safe fetch for %s: %d total accounts.", label, len(users_list))
        return users_list

    async def run_audit(self, send_digest_now: bool = True) -> FollowerDiff | None:
        """Run a full follower & following audit safely, store snapshot, and notify."""
        if self._is_running_audit:
            logger.warning("Follower audit already in progress. Skipping concurrent run.")
            return None

        self._is_running_audit = True
        try:
            target = self.config.target_handle.lower()
            logger.info("Beginning safe follower audit for @%s", target)

            if not self.fetcher_client:
                raise RuntimeError("Fetcher client is not initialized.")

            # 1. Resolve user ID
            user_obj = await self.fetcher_client.get_user_by_screen_name(target)
            target_user_id = user_obj.id

            # 2. Safely fetch followers
            followers_raw = await self.fetch_user_list_safely(
                self.fetcher_client.get_user_followers,
                target_user_id,
                label=f"@{target} followers",
            )

            # 3. Intermission delay between followers and following
            intermission = random.uniform(self.config.min_request_delay_seconds, self.config.max_request_delay_seconds)
            logger.info("Intermission between followers & following: sleeping %.1fs...", intermission)
            await asyncio.sleep(intermission)

            # 4. Safely fetch following
            following_raw = await self.fetch_user_list_safely(
                self.fetcher_client.get_user_following,
                target_user_id,
                label=f"@{target} following",
            )

            # 5. Retrieve previous snapshot to compute diff
            latest_snap = self.storage.get_latest_follower_snapshot(target)
            is_first_run = latest_snap is None

            prev_followers: dict[int, FollowerUser] = {}
            prev_following: dict[int, FollowerUser] = {}
            if latest_snap:
                snap_id = latest_snap["id"]
                users_rows = self.storage.get_snapshot_users(snap_id)
                for r in users_rows:
                    u = FollowerUser(id=r["user_id"], screen_name=r["screen_name"], name=r["name"])
                    if r["relationship"] == "follower":
                        prev_followers[u.id] = u
                    elif r["relationship"] == "following":
                        prev_following[u.id] = u

            curr_followers = {u.id: u for u in followers_raw}
            curr_following = {u.id: u for u in following_raw}

            diff = self.compute_diff(
                prev_followers=prev_followers,
                prev_following=prev_following,
                curr_followers=curr_followers,
                curr_following=curr_following,
                is_first_run=is_first_run,
            )
            diff.target_handle = target

            # 6. Save current snapshot in SQLite
            self.storage.save_follower_snapshot(
                target_handle=target,
                followers=followers_raw,
                following=following_raw,
                recorded_at=datetime.now(),
            )
            logger.info("Saved follower snapshot in SQLite for @%s", target)

            # 7. Deliver rich digest via Telegram if enabled
            if send_digest_now and self.config.send_telegram_digest and self.notifier:
                digest_msg = format_follower_digest(diff)
                await self.notifier.send_message(digest_msg)
                logger.info("Delivered follower report digest to Telegram.")

            return diff

        except Exception as exc:
            logger.error("Error during follower audit for @%s: %s", self.config.target_handle, exc, exc_info=True)
            if self.notifier:
                await self.notifier.send_alert(
                    "follower_audit_error",
                    f"Daily Follower Tracker failed: {exc}",
                )
            return None
        finally:
            self._is_running_audit = False
