"""Unit tests for fetcher error handling, tweet parsing, and session initialization."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from config import XAccountConfig
from fetcher import (
    TwikitFetcher,
    RateLimitException,
    AccountLockedException,
    AccountSuspendedException,
    SessionExpiredException,
    NetworkException,
    FetcherException,
)
from twikit import errors


def test_fetcher_error_mapping():
    cfg = XAccountConfig(username="u", password="p", list_id="123")
    fetcher = TwikitFetcher(cfg)

    # 429
    with pytest.raises(RateLimitException):
        fetcher._handle_twikit_error(errors.TooManyRequests("Rate limited"))

    # Locked
    with pytest.raises(AccountLockedException):
        fetcher._handle_twikit_error(errors.AccountLocked("Locked"))

    # Suspended
    with pytest.raises(AccountSuspendedException):
        fetcher._handle_twikit_error(errors.AccountSuspended("Suspended"))

    # Unauthorized
    with pytest.raises(SessionExpiredException):
        fetcher._handle_twikit_error(errors.Unauthorized("Unauthorized"))

    # LoginRetired or flow broken
    with pytest.raises(SessionExpiredException):
        fetcher._handle_twikit_error(Exception("LoginFlow is currently not accessible"))

    # Timeout
    with pytest.raises(NetworkException):
        fetcher._handle_twikit_error(errors.RequestTimeout("Timeout"))

    # Generic
    with pytest.raises(FetcherException):
        fetcher._handle_twikit_error(Exception("Something generic"))


@pytest.mark.asyncio
async def test_fetcher_initialize_with_tokens():
    cfg = XAccountConfig(
        auth_token="dummy_auth_token",
        ct0="dummy_ct0",
        cookies_path="/tmp/test_notifyme_cookies.json",
    )
    fetcher = TwikitFetcher(cfg)

    with patch("twikit.Client") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance

        await fetcher.initialize()

        mock_instance.set_cookies.assert_called_once_with({
            "auth_token": "dummy_auth_token",
            "ct0": "dummy_ct0",
        })


@pytest.mark.asyncio
async def test_fetcher_initialize_missing_everything():
    cfg = XAccountConfig(username="", password="", auth_token="", ct0="", cookies_path="/tmp/non_existent.json")
    fetcher = TwikitFetcher(cfg)

    with pytest.raises(SessionExpiredException):
        await fetcher.initialize()


@pytest.mark.asyncio
async def test_fetch_list_tweets_parsing():
    cfg = XAccountConfig(username="u", password="p", list_id="123")
    fetcher = TwikitFetcher(cfg)

    mock_client = MagicMock()
    mock_tweet = MagicMock()
    mock_tweet.id = "9876543210"
    mock_tweet.full_text = "Parsing test tweet"
    mock_tweet.text = None
    mock_tweet.in_reply_to = None
    mock_tweet.retweeted_tweet = None
    mock_tweet.is_quote_status = False
    mock_tweet.created_at = "Mon Oct 26 10:00:00 +0000 2026"

    user = MagicMock()
    user.screen_name = "cool_dev"
    mock_tweet.user = user

    media_obj = MagicMock()
    media_obj.media_url_https = "https://pbs.twimg.com/media/pic.jpg"
    mock_tweet.media = [media_obj]

    mock_client.get_list_tweets = AsyncMock(return_value=[mock_tweet])
    fetcher.client = mock_client

    tweets = await fetcher.fetch_list_tweets("123", count=10)
    assert len(tweets) == 1
    t = tweets[0]
    assert t.id == 9876543210
    assert t.author_handle == "cool_dev"
    assert t.text == "Parsing test tweet"
    assert t.is_reply is False
    assert t.is_retweet is False
    assert t.media == ["https://pbs.twimg.com/media/pic.jpg"]
    assert t.url == "https://x.com/cool_dev/status/9876543210"
