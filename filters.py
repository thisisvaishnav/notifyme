"""Tweet data model and filtering engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from config import FilterConfig, AccountOverrideConfig


@dataclass
class TweetData:
    """Standardized tweet representation across fetchers."""
    id: int
    text: str
    author_handle: str
    is_reply: bool
    is_retweet: bool
    is_quote: bool
    created_at: str
    media: list[str] = field(default_factory=list)
    url: str = ""

    def __post_init__(self):
        if not self.url:
            self.url = f"https://x.com/{self.author_handle}/status/{self.id}"


class FilterEngine:
    """Evaluates whether a tweet should be delivered to Telegram based on user rules."""

    def __init__(self, config: FilterConfig):
        self.config = config

    def should_notify(self, tweet: TweetData) -> tuple[bool, str]:
        """Check if the tweet satisfies all delivery rules.

        Returns:
            A tuple of (allowed: bool, reason: str).
        """
        handle = tweet.author_handle.lower().lstrip("@")
        override: AccountOverrideConfig | None = self.config.account_overrides.get(handle)

        # 1. Reply check
        include_replies = (
            override.include_replies
            if override and override.include_replies is not None
            else self.config.include_replies
        )
        if tweet.is_reply and not include_replies:
            return False, "Filtered out: reply"

        # 2. Retweet check
        include_retweets = (
            override.include_retweets
            if override and override.include_retweets is not None
            else self.config.include_retweets
        )
        if tweet.is_retweet and not include_retweets:
            return False, "Filtered out: retweet"

        # 3. Quote tweet check
        include_quotes = (
            override.include_quotes
            if override and override.include_quotes is not None
            else self.config.include_quotes
        )
        if tweet.is_quote and not include_quotes:
            return False, "Filtered out: quote tweet"

        # 4. Keyword blocklist
        blocklist = (
            override.keyword_blocklist
            if override and override.keyword_blocklist is not None
            else self.config.keyword_blocklist
        )
        lower_text = tweet.text.lower()
        for blocked_kw in blocklist:
            if blocked_kw.lower() in lower_text:
                return False, f"Filtered out: blocklisted keyword '{blocked_kw}'"

        # 5. Keyword allowlist
        allowlist = (
            override.keyword_allowlist
            if override and override.keyword_allowlist is not None
            else self.config.keyword_allowlist
        )
        if allowlist:
            matched = any(kw.lower() in lower_text for kw in allowlist)
            if not matched:
                return False, "Filtered out: allowlist requirement not met"

        return True, "passed"
