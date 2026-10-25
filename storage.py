"""SQLite storage and deduplication engine."""

from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from typing import Any


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
