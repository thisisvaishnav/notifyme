"""Unit tests for Telegram notification formatting, truncation, alert cooldowns, and network dispatch."""

import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from notifier import TelegramNotifier
from filters import TweetData
from config import TelegramConfig, AlertConfig


@pytest.fixture
def notifier():
    tg_config = TelegramConfig(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        chat_id="987654321",
    )
    alert_config = AlertConfig(
        max_consecutive_failures=5,
        inactivity_alert_minutes=10,
        alert_cooldown_minutes=30,
    )
    return TelegramNotifier(tg_config, alert_config)


def test_format_tweet_html_escaping(notifier: TelegramNotifier):
    tweet = TweetData(
        id=1234567890123456,
        text="Testing <script>alert('xss')</script> & other special \"symbols\" > <",
        author_handle="developer_guy",
        is_reply=False,
        is_retweet=False,
        is_quote=False,
        created_at="Sun Oct 25 08:00:00 +0000 2026",
        media=[],
        url="https://x.com/developer_guy/status/1234567890123456",
    )
    formatted = notifier.format_tweet_message(tweet)

    assert "<script>" not in formatted
    assert "&lt;script&gt;" in formatted
    assert "&amp;" in formatted
    assert "https://x.com/developer_guy/status/1234567890123456" in formatted
    assert "@developer_guy" in formatted


def test_format_tweet_with_media_hints(notifier: TelegramNotifier):
    tweet = TweetData(
        id=123456,
        text="Check out this photo and video!",
        author_handle="photographer",
        is_reply=False,
        is_retweet=False,
        is_quote=False,
        created_at="Sun Oct 25 08:00:00 +0000 2026",
        media=["https://pbs.twimg.com/media/pic1.jpg", "https://video.twimg.com/v.mp4"],
        url="https://x.com/photographer/status/123456",
    )
    formatted = notifier.format_tweet_message(tweet)
    assert "📷/🎬" in formatted or "Media" in formatted


def test_telegram_character_limit_truncation(notifier: TelegramNotifier):
    long_text = "A" * 5000
    tweet = TweetData(
        id=999999,
        text=long_text,
        author_handle="longposter",
        is_reply=False,
        is_retweet=False,
        is_quote=False,
        created_at="Sun Oct 25 08:00:00 +0000 2026",
        media=[],
        url="https://x.com/longposter/status/999999",
    )
    formatted = notifier.format_tweet_message(tweet)
    assert len(formatted) <= 4096
    assert "..." in formatted


def test_alert_cooldown_logic(notifier: TelegramNotifier):
    alert_type = "session_expired"

    assert notifier.can_send_alert(alert_type) is True
    notifier.record_alert_sent(alert_type)

    assert notifier.can_send_alert(alert_type) is False

    notifier._alert_timestamps[alert_type] = time.time() - (31 * 60)
    assert notifier.can_send_alert(alert_type) is True


@pytest.mark.asyncio
async def test_send_alert_and_recovery(notifier: TelegramNotifier):
    notifier._send_raw_message = AsyncMock(return_value=True)

    # 1. Send alert
    success = await notifier.send_alert("session_expired", "Session cookie missing")
    assert success is True
    assert notifier._send_raw_message.call_count == 1
    assert "session_expired" in notifier._active_alerts

    # 2. Duplicate alert suppressed
    suppressed = await notifier.send_alert("session_expired", "Session cookie missing again")
    assert suppressed is False
    assert notifier._send_raw_message.call_count == 1

    # 3. Recovery alert
    recovered = await notifier.send_recovery_alert("session_expired", "Session refreshed")
    assert recovered is True
    assert notifier._send_raw_message.call_count == 2
    assert "session_expired" not in notifier._active_alerts

    # 4. Duplicate recovery does nothing
    repeat_recovery = await notifier.send_recovery_alert("session_expired", "Already recovered")
    assert repeat_recovery is False
    assert notifier._send_raw_message.call_count == 2


@pytest.mark.asyncio
async def test_send_tweet_notification(notifier: TelegramNotifier):
    notifier._send_raw_message = AsyncMock(return_value=True)

    tweet = TweetData(
        id=55555,
        text="Alert tweet",
        author_handle="sender",
        is_reply=False,
        is_retweet=False,
        is_quote=False,
        created_at="now",
    )

    sent = await notifier.send_tweet_notification(tweet)
    assert sent is True
    assert notifier._send_raw_message.call_count == 1
