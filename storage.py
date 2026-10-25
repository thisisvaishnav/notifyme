"""SQLite storage and deduplication engine."""

from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from follower_tracker import FollowerUser


class SQLiteStorage:
    """Manages persistent SQLite state for tweet deduplication, baseline tracking, and poll history."""

    def __init__(self, db_path: str = "data/monitor.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Create a thread-safe connection with row dictionary access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        """Create necessary database tables and indexes."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Metadata table for key-value state (baseline flag, last seen tweet ID)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Notified tweets table for strict deduplication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notified_tweets (
                    tweet_id INTEGER PRIMARY KEY,
                    author_handle TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    media_urls TEXT
                )
            """)

            # Poll history for logging and dashboard telemetry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS poll_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    tweets_found INTEGER DEFAULT 0,
                    tweets_notified INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """)

            # Follower tracker snapshot table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS follower_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_handle TEXT NOT NULL,
                    total_followers INTEGER NOT NULL,
                    total_following INTEGER NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Follower and following users for each snapshot
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS follower_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    screen_name TEXT NOT NULL,
                    name TEXT,
                    relationship TEXT NOT NULL, -- 'follower' or 'following'
                    FOREIGN KEY (snapshot_id) REFERENCES follower_snapshots(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_follower_users_snap ON follower_users(snapshot_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_follower_users_user_rel ON follower_users(user_id, relationship)")

            conn.commit()

    def is_baseline_set(self) -> bool:
        """Check if the initial silent baseline has already been established."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'baseline_set'")
            row = cursor.fetchone()
            return bool(row and row["value"].lower() == "true")

    def set_baseline(self, highest_tweet_id: int) -> None:
        """Set the baseline tweet ID silently on the very first run."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('baseline_set', 'true')"
            )
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_seen_id', ?)",
                (str(highest_tweet_id),),
            )
            conn.commit()

    def get_last_seen_id(self) -> int:
        """Retrieve the highest tweet snowflake ID seen so far."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_seen_id'")
            row = cursor.fetchone()
            if row and row["value"]:
                try:
                    return int(row["value"])
                except ValueError:
                    return 0
            return 0

    def update_last_seen_id(self, tweet_id: int) -> None:
        """Update last seen tweet ID if the given snowflake ID is greater."""
        current = self.get_last_seen_id()
        if tweet_id > current:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_seen_id', ?)",
                    (str(tweet_id),),
                )
                conn.commit()

    def is_tweet_notified(self, tweet_id: int) -> bool:
        """Check if a tweet ID has already been notified."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM notified_tweets WHERE tweet_id = ?",
                (tweet_id,),
            )
            return cursor.fetchone() is not None

    def mark_tweet_notified(
        self,
        tweet_id: int,
        author_handle: str,
        text: str,
        created_at: str,
        media_urls: list[str] | None = None,
    ) -> None:
        """Record that a tweet has been successfully delivered."""
        media_json = json.dumps(media_urls or [])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO notified_tweets
                (tweet_id, author_handle, text, created_at, media_urls)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tweet_id, author_handle, text, created_at, media_json),
            )
            conn.commit()

    def record_poll(
        self,
        status: str,
        tweets_found: int = 0,
        tweets_notified: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Record the outcome of a poll cycle."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO poll_history
                (status, tweets_found, tweets_notified, error_message)
                VALUES (?, ?, ?, ?)
                """,
                (status, tweets_found, tweets_notified, error_message),
            )
            conn.commit()

    def get_recent_notified(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent notified tweets ordered newest first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tweet_id, author_handle, text, created_at, notified_at, media_urls
                FROM notified_tweets
                ORDER BY tweet_id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["media_urls"] = json.loads(item.get("media_urls") or "[]")
                except Exception:
                    item["media_urls"] = []
                results.append(item)
            return results

    def get_recent_polls(self, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve recent poll attempts ordered newest first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, timestamp, status, tweets_found, tweets_notified, error_message
                FROM poll_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """Aggregate stats for the dashboard and status reporting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total_notified FROM notified_tweets")
            total_notified = cursor.fetchone()["total_notified"]

            cursor.execute("SELECT COUNT(*) AS total_polls FROM poll_history")
            total_polls = cursor.fetchone()["total_polls"]

            cursor.execute("SELECT COUNT(*) AS total_errors FROM poll_history WHERE status = 'error'")
            total_errors = cursor.fetchone()["total_errors"]

            cursor.execute("SELECT timestamp FROM poll_history WHERE status = 'success' ORDER BY id DESC LIMIT 1")
            last_success_row = cursor.fetchone()
            last_success = last_success_row["timestamp"] if last_success_row else None

            cursor.execute("SELECT timestamp, status, error_message FROM poll_history ORDER BY id DESC LIMIT 1")
            last_poll_row = cursor.fetchone()
            last_poll = dict(last_poll_row) if last_poll_row else None

            return {
                "total_notified_tweets": total_notified,
                "total_polls": total_polls,
                "total_errors": total_errors,
                "last_successful_poll": last_success,
                "last_poll": last_poll,
                "last_seen_id": self.get_last_seen_id(),
                "baseline_set": self.is_baseline_set(),
            }

    # Follower Tracker Storage Methods
    def save_follower_snapshot(
        self,
        target_handle: str,
        followers: list[FollowerUser],
        following: list[FollowerUser],
        recorded_at: datetime | None = None,
    ) -> int:
        """Save a new follower/following snapshot with its complete roster."""
        recorded_time = recorded_at.strftime("%Y-%m-%d %H:%M:%S") if recorded_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO follower_snapshots (target_handle, total_followers, total_following, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (target_handle.lower(), len(followers), len(following), recorded_time),
            )
            snapshot_id = cursor.lastrowid

            rows_to_insert = []
            for u in followers:
                rows_to_insert.append((snapshot_id, u.id, u.screen_name, u.name, "follower"))
            for u in following:
                rows_to_insert.append((snapshot_id, u.id, u.screen_name, u.name, "following"))

            cursor.executemany(
                """
                INSERT INTO follower_users (snapshot_id, user_id, screen_name, name, relationship)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
            conn.commit()
            return snapshot_id

    def get_latest_follower_snapshot(self, target_handle: str) -> dict[str, Any] | None:
        """Retrieve the most recent snapshot for the target handle."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, target_handle, total_followers, total_following, recorded_at
                FROM follower_snapshots
                WHERE target_handle = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (target_handle.lower(),),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recent_follower_snapshots(self, target_handle: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve recent snapshots for the target handle."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, target_handle, total_followers, total_following, recorded_at
                FROM follower_snapshots
                WHERE target_handle = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (target_handle.lower(), limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_snapshot_users(self, snapshot_id: int, relationship: str | None = None) -> list[dict[str, Any]]:
        """Fetch users from a specific snapshot, optionally filtered by relationship type ('follower' or 'following')."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if relationship:
                cursor.execute(
                    """
                    SELECT user_id, screen_name, name, relationship
                    FROM follower_users
                    WHERE snapshot_id = ? AND relationship = ?
                    """,
                    (snapshot_id, relationship),
                )
            else:
                cursor.execute(
                    """
                    SELECT user_id, screen_name, name, relationship
                    FROM follower_users
                    WHERE snapshot_id = ?
                    """,
                    (snapshot_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_not_following_back(self, target_handle: str) -> list[dict[str, Any]]:
        """Retrieve accounts that target_handle follows, but who do not follow back in the latest snapshot."""
        latest = self.get_latest_follower_snapshot(target_handle)
        if not latest:
            return []

        snapshot_id = latest["id"]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, screen_name, name
                FROM follower_users
                WHERE snapshot_id = ? AND relationship = 'following'
                  AND user_id NOT IN (
                      SELECT user_id FROM follower_users
                      WHERE snapshot_id = ? AND relationship = 'follower'
                  )
                ORDER BY screen_name COLLATE NOCASE ASC
                """,
                (snapshot_id, snapshot_id),
            )
            return [dict(row) for row in cursor.fetchall()]


StorageEngine = SQLiteStorage
