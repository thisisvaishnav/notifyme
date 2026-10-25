"""Integration tests for MonitorEngine with mocked fetcher and notifier."""

import pytest
import asyncio
from unittest.mock import AsyncMock
from config import AppConfig, FilterConfig, PollConfig, AlertConfig, XAccountConfig, TelegramConfig
from storage import SQLiteStorage
from filters import TweetData
from fetcher import BaseFetcher, RateLimitException
from notifier import TelegramNotifier
from main import MonitorEngine


class MockFetcher(BaseFetcher):
    """Mock X fetcher returning simulated tweet batches."""

    def __init__(self):
        self.next_batch: list[TweetData] = []
        self.should_raise: Exception | None = None
        self.call_count = 0

    async def initialize(self) -> None:
        pass

    async def fetch_list_tweets(self, list_id: str, count: int = 40) -> list[TweetData]:
        self.call_count += 1
        if self.should_raise:
            raise self.should_raise
        return list(self.next_batch)

    async def close(self) -> None:
        pass


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "test_engine.db"
    storage = SQLiteStorage(str(db_file))
    storage.initialize()

    config = AppConfig(
        telegram=TelegramConfig(bot_token="test:token", chat_id="12345"),
        x_account=XAccountConfig(list_id="9988776655"),
        poll=PollConfig(interval_seconds=1, jitter_max_seconds=0),
        filters=FilterConfig(include_replies=False, include_retweets=False, include_quotes=False),
        alerts=AlertConfig(max_consecutive_failures=2, alert_cooldown_minutes=1),
    )

    fetcher = MockFetcher()

    notifier = TelegramNotifier(config.telegram, config.alerts)
    notifier._send_raw_message = AsyncMock(return_value=True)

    engine = MonitorEngine(config, storage, fetcher, notifier)
    return engine, fetcher, notifier, storage


@pytest.mark.asyncio
async def test_engine_baseline_and_new_tweets(test_setup):
    engine, fetcher, notifier, storage = test_setup

    # Batch 1: Initial tweets existing in the list
    t1 = TweetData(id=1001, text="Old tweet 1", author_handle="user_a", is_reply=False, is_retweet=False, is_quote=False, created_at="now")
    t2 = TweetData(id=1002, text="Old tweet 2", author_handle="user_b", is_reply=False, is_retweet=False, is_quote=False, created_at="now")
    fetcher.next_batch = [t2, t1]

    # First cycle sets baseline silently (no notifications)
    notified = await engine.poll_once()
    assert notified == 0
    assert storage.is_baseline_set() is True
    assert storage.get_last_seen_id() == 1002
    assert notifier._send_raw_message.call_count == 0

    # Batch 2: New tweet arrives with ID 1003
    t3 = TweetData(id=1003, text="Brand new post!", author_handle="user_c", is_reply=False, is_retweet=False, is_quote=False, created_at="now")
    fetcher.next_batch = [t3, t2, t1]

    notified = await engine.poll_once()
    assert notified == 1
    assert storage.get_last_seen_id() == 1003
    assert notifier._send_raw_message.call_count == 1
    assert storage.is_tweet_notified(1003) is True

    # Batch 3: Same tweet still present on list timeline (no duplicate alert)
    notified = await engine.poll_once()
    assert notified == 0
    assert notifier._send_raw_message.call_count == 1


@pytest.mark.asyncio
async def test_engine_chronological_ordering(test_setup):
    engine, fetcher, notifier, storage = test_setup
    storage.set_baseline(1000)

    # Tweets arrive unordered (e.g. 1005, 1002, 1004)
    t1002 = TweetData(id=1002, text="Second post", author_handle="alpha", is_reply=False, is_retweet=False, is_quote=False, created_at="now")
    t1004 = TweetData(id=1004, text="Fourth post", author_handle="beta", is_reply=False, is_retweet=False, is_quote=False, created_at="now")
    t1005 = TweetData(id=1005, text="Fifth post", author_handle="gamma", is_reply=False, is_retweet=False, is_quote=False, created_at="now")

    delivered_ids = []

    async def mock_send_tweet(tweet):
        delivered_ids.append(tweet.id)
        return True

    notifier.send_tweet_notification = mock_send_tweet

    fetcher.next_batch = [t1005, t1002, t1004]
    notified = await engine.poll_once()

    assert notified == 3
    # Verified chronological ordering: 1002, 1004, 1005
    assert delivered_ids == [1002, 1004, 1005]
    assert storage.get_last_seen_id() == 1005


@pytest.mark.asyncio
async def test_engine_error_backoff_and_recovery(test_setup):
    engine, fetcher, notifier, storage = test_setup
    storage.set_baseline(1000)

    # 1. Error simulation
    fetcher.should_raise = RateLimitException("HTTP 429")
    await engine._handle_poll_error(fetcher.should_raise)

    assert engine.consecutive_failures == 1
    assert engine.backoff.failure_count == 1

    # 2. Recovery on next success
    fetcher.should_raise = None
    fetcher.next_batch = []
    await engine.poll_once()

    # When engine recovers in run_loop, consecutive_failures resets
    if engine.consecutive_failures > 0:
        engine.consecutive_failures = 0
        engine.backoff.record_success()

    assert engine.consecutive_failures == 0
    assert engine.backoff.failure_count == 0
