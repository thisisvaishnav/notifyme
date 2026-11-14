"""SQLite storage for tracking seen GitHub issues and repository sync state."""

from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class IssueStorage:
    """Thread-safe SQLite storage using WAL mode and UTC timestamps."""

    CURRENT_SCHEMA_VERSION = 1

    def __init__(self, db_path: str = "github_issue_monitor/data/issues.db"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_db(self) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_issues (
                    repo TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    seen_at TEXT NOT NULL,
                    PRIMARY KEY (repo, issue_number)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repo_metadata (
                    repo TEXT PRIMARY KEY,
                    etag TEXT,
                    baselined INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)

            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_v = row[0] if (row and row[0] is not None) else 0

            if current_v < self.CURRENT_SCHEMA_VERSION:
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (self.CURRENT_SCHEMA_VERSION, self._now_utc()),
                )
            conn.commit()

    def is_seen(self, repo: str, issue_number: int) -> bool:
        """Check if an issue was already seen and processed."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM seen_issues WHERE repo = ? AND issue_number = ?",
                (repo.strip().lower(), issue_number),
            )
            return cursor.fetchone() is not None

    def mark_seen(self, repo: str, issue_number: int, title: str = "") -> None:
        """Mark an issue as seen using INSERT OR IGNORE."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO seen_issues (repo, issue_number, title, seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (repo.strip().lower(), issue_number, title.strip(), self._now_utc()),
            )
            conn.commit()

    def save_etag(self, repo: str, etag: str) -> None:
        """Save latest HTTP ETag for repository."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO repo_metadata (repo, etag, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    etag = excluded.etag,
                    updated_at = excluded.updated_at
                """,
                (repo.strip().lower(), etag.strip(), self._now_utc()),
            )
            conn.commit()

    def get_etag(self, repo: str) -> str | None:
        """Retrieve stored HTTP ETag for repository, if any."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT etag FROM repo_metadata WHERE repo = ?",
                (repo.strip().lower(),),
            )
            row = cursor.fetchone()
            return row["etag"] if row and row["etag"] else None

    def is_baselined(self, repo: str) -> bool:
        """Check if initial repository baseline run was performed."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT baselined FROM repo_metadata WHERE repo = ?",
                (repo.strip().lower(),),
            )
            row = cursor.fetchone()
            return bool(row["baselined"]) if row else False

    def set_baselined(self, repo: str) -> None:
        """Mark initial repository baseline run as complete."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO repo_metadata (repo, baselined, updated_at)
                VALUES (?, 1, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    baselined = 1,
                    updated_at = excluded.updated_at
                """,
                (repo.strip().lower(), self._now_utc()),
            )
            conn.commit()

    def close(self) -> None:
        """No persistent connection pool to clean up in sqlite3 one-off connects."""
        pass
