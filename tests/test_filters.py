"""Unit tests for tweet filtering logic."""

import pytest
from filters import FilterEngine, TweetData
from config import FilterConfig, AccountOverrideConfig


@pytest.fixture
def base_config() -> FilterConfig:
    return FilterConfig(
        include_replies=False,
        include_retweets=False,
        include_quotes=False,
        keyword_allowlist=[],
        keyword_blocklist=[],
        account_overrides={},
    )


def make_tweet(
    tweet_id: int = 1234567890,
    text: str = "Hello world!",
    author_handle: str = "elonmusk",
    is_reply: bool = False,
    is_retweet: bool = False,
    is_quote: bool = False,
) -> TweetData:
    return TweetData(
        id=tweet_id,
        text=text,
        author_handle=author_handle,
        is_reply=is_reply,
        is_retweet=is_retweet,
        is_quote=is_quote,
        created_at="Sun Oct 25 08:00:00 +0000 2026",
        media=[],
        url=f"https://x.com/{author_handle}/status/{tweet_id}",
    )


def test_allow_original_tweet(base_config: FilterConfig):
    engine = FilterEngine(base_config)
    tweet = make_tweet()
    allowed, reason = engine.should_notify(tweet)
    assert allowed is True
    assert reason == "passed"


def test_reject_reply_by_default(base_config: FilterConfig):
    engine = FilterEngine(base_config)
    tweet = make_tweet(is_reply=True)
    allowed, reason = engine.should_notify(tweet)
    assert allowed is False
    assert "reply" in reason.lower()


def test_reject_retweet_by_default(base_config: FilterConfig):
    engine = FilterEngine(base_config)
    tweet = make_tweet(is_retweet=True)
    allowed, reason = engine.should_notify(tweet)
    assert allowed is False
    assert "retweet" in reason.lower()


def test_reject_quote_by_default(base_config: FilterConfig):
    engine = FilterEngine(base_config)
    tweet = make_tweet(is_quote=True)
    allowed, reason = engine.should_notify(tweet)
    assert allowed is False
    assert "quote" in reason.lower()


def test_keyword_allowlist(base_config: FilterConfig):
    base_config.keyword_allowlist = ["bitcoin", "crypto"]
    engine = FilterEngine(base_config)

    # Tweet without keyword should be blocked
    tweet1 = make_tweet(text="Just having coffee")
    allowed, reason = engine.should_notify(tweet1)
    assert allowed is False
    assert "allowlist" in reason.lower()

    # Tweet with keyword (case-insensitive) should pass
    tweet2 = make_tweet(text="Big news for BitCoin today!")
    allowed, reason = engine.should_notify(tweet2)
    assert allowed is True


def test_keyword_blocklist(base_config: FilterConfig):
    base_config.keyword_blocklist = ["giveaway", "airdrop"]
    engine = FilterEngine(base_config)

    # Tweet with blocked word should be rejected
    tweet1 = make_tweet(text="Free crypto airdrop happening now!")
    allowed, reason = engine.should_notify(tweet1)
    assert allowed is False
    assert "blocklist" in reason.lower()

    # Normal tweet should pass
    tweet2 = make_tweet(text="Working on our new release.")
    allowed, reason = engine.should_notify(tweet2)
    assert allowed is True


def test_per_account_override(base_config: FilterConfig):
    # Base config excludes retweets
    base_config.account_overrides = {
        "special_user": AccountOverrideConfig(
            include_retweets=True,
            include_quotes=True,
            keyword_allowlist=["launch"],
        )
    }
    engine = FilterEngine(base_config)

    # Special user can pass retweet if it has the keyword
    tweet1 = make_tweet(
        author_handle="special_user",
        is_retweet=True,
        text="Rocket launch scheduled for tomorrow",
    )
    allowed, reason = engine.should_notify(tweet1)
    assert allowed is True

    # Special user retweet without keyword is rejected by keyword allowlist
    tweet2 = make_tweet(
        author_handle="special_user",
        is_retweet=True,
        text="Good morning everyone",
    )
    allowed, reason = engine.should_notify(tweet2)
    assert allowed is False
