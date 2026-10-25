"""Unit tests for SQLite storage and deduplication."""

import pytest
import os
import tempfile
from storage import SQLiteStorage


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    storage = SQLiteStorage(path)
    storage.initialize()
    yield storage
    if os.path.exists(path):
        os.remove(path)


def test_initial_baseline_state(temp_db: SQLiteStorage):
    assert temp_db.is_baseline_set() is False
    assert temp_db.get_last_seen_id() == 0


def test_set_baseline(temp_db: SQLiteStorage):
    temp_db.set_baseline(1849123456789012345)
    assert temp_db.is_baseline_set() is True
    assert temp_db.get_last_seen_id() == 1849123456789012345


def test_update_last_seen_id_snowflake(temp_db: SQLiteStorage):
    id1 = 1000000000000000001
    id2 = 1000000000000000002
    temp_db.set_baseline(id1)
    assert temp_db.get_last_seen_id() == id1

    # Update with higher ID
    temp_db.update_last_seen_id(id2)
    assert temp_db.get_last_seen_id() == id2

    # Lower ID should NOT regress the last seen ID
    temp_db.update_last_seen_id(id1)
    assert temp_db.get_last_seen_id() == id2


def test_deduplication(temp_db: SQLiteStorage):
    tweet_id = 1849000111222333444
    assert temp_db.is_tweet_notified(tweet_id) is False

    temp_db.mark_tweet_notified(
        tweet_id=tweet_id,
        author_handle="sataboriginal",
        text="A test tweet content",
        created_at="Sun Oct 25 08:00:00 +0000 2026",
        media_urls=["https://pbs.twimg.com/media/pic1.jpg"],
    )

    assert temp_db.is_tweet_notified(tweet_id) is True

    # Check recent notified retrieval
    recent = temp_db.get_recent_notified(limit=10)
    assert len(recent) == 1
    assert recent[0]["tweet_id"] == tweet_id
    assert recent[0]["author_handle"] == "sataboriginal"


def test_poll_history_and_stats(temp_db: SQLiteStorage):
    temp_db.record_poll(
        status="success",
        tweets_found=5,
        tweets_notified=2,
        error_message=None,
    )
    temp_db.record_poll(
        status="error",
        tweets_found=0,
        tweets_notified=0,
        error_message="HTTP 429 Too Many Requests",
    )

    history = temp_db.get_recent_polls(limit=5)
    assert len(history) == 2
    assert history[0]["status"] == "error"
    assert history[1]["status"] == "success"

    stats = temp_db.get_stats()
    assert stats["total_polls"] == 2
    assert stats["total_errors"] == 1
    assert stats["total_notified_tweets"] == 0  # no tweet notified in this test yet
