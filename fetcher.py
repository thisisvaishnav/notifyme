"""Swappable X fetcher interface and Twikit implementation."""

from __future__ import annotations
import os
import logging
from abc import ABC, abstractmethod
from typing import Any
from config import XAccountConfig
from filters import TweetData

logger = logging.getLogger("notifyme.fetcher")


class FetcherException(Exception):
    """Base exception for fetcher errors."""
    pass


class RateLimitException(FetcherException):
    """Raised when X responds with HTTP 429 Too Many Requests."""
    pass


class SessionExpiredException(FetcherException):
    """Raised when X cookies/session are invalid or expired."""
    pass


class AccountLockedException(FetcherException):
    """Raised when the data account is locked or challenged by captcha."""
    pass


class AccountSuspendedException(FetcherException):
    """Raised when the data account has been suspended."""
    pass


class NetworkException(FetcherException):
    """Raised on connection timeout or network level failures."""
    pass


class BaseFetcher(ABC):
    """Abstract interface for fetching tweets from X.

    Allows swapping the unofficial twikit scraper with the official X API v2
    or an alternate client without touching any core monitor or notifier logic.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Prepare the client session, load cookies or authenticate."""
        pass

    @abstractmethod
    async def fetch_list_tweets(self, list_id: str, count: int = 40) -> list[TweetData]:
        """Fetch the most recent tweets from an X List."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Tear down any network connections."""
        pass


class TwikitFetcher(BaseFetcher):
    """Asynchronous X fetcher implementation powered by twikit."""

    def __init__(self, config: XAccountConfig):
        self.config = config
        self.client: Any = None

    async def initialize(self) -> None:
        """Initialize twikit client and authenticate using saved cookies or credentials."""
        from twikit import Client

        self.client = Client(language="en-US")
        cookies_file = self.config.cookies_path

        if os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 10:
            try:
                logger.info("Loading existing X session from %s", cookies_file)
                self.client.load_cookies(cookies_file)
                return
            except Exception as exc:
                logger.warning("Failed to load existing cookies from %s: %s. Attempting fresh login...", cookies_file, exc)

        await self._login_and_save_cookies()

    async def _login_and_save_cookies(self) -> None:
        """Execute a fresh login and persist cookies to disk."""
        if not self.config.username or not self.config.password:
            raise SessionExpiredException(
                "X username or password not provided in environment/.env; cannot authenticate."
            )

        logger.info("Attempting fresh login to X for user '%s'...", self.config.username)
        try:
            await self.client.login(
                auth_info_1=self.config.username,
                auth_info_2=self.config.email or None,
                password=self.config.password,
                totp_secret=self.config.totp_secret or None,
                cookies_file=self.config.cookies_path,
            )
            logger.info("Successfully authenticated with X. Cookies saved to %s", self.config.cookies_path)
        except Exception as exc:
            self._handle_twikit_error(exc, is_during_login=True)

    async def fetch_list_tweets(self, list_id: str, count: int = 40) -> list[TweetData]:
        """Fetch the latest tweets from the specified X List timeline."""
        if not self.client:
            await self.initialize()

        try:
            raw_tweets = await self.client.get_list_tweets(list_id=str(list_id), count=count)
        except Exception as exc:
            # Check if this might be an expired session that can be recovered with one re-login
            from twikit.errors import Unauthorized, Forbidden
            if isinstance(exc, (Unauthorized, Forbidden)):
                logger.warning("Session appears expired during poll: %s. Attempting one re-login...", exc)
                try:
                    await self._login_and_save_cookies()
                    raw_tweets = await self.client.get_list_tweets(list_id=str(list_id), count=count)
                except Exception as retry_exc:
                    self._handle_twikit_error(retry_exc)
            else:
                self._handle_twikit_error(exc)

        parsed_list: list[TweetData] = []
        for t in raw_tweets:
            try:
                tweet_id = int(t.id)
                text = getattr(t, "full_text", None) or getattr(t, "text", "") or ""

                user_obj = getattr(t, "user", None)
                author = getattr(user_obj, "screen_name", "") if user_obj else ""
                if not author:
                    # Fallback to legacy structure if present
                    legacy = getattr(t, "_legacy", {})
                    author = legacy.get("user_id_str", "unknown")

                is_reply = bool(getattr(t, "in_reply_to", None))
                is_retweet = bool(getattr(t, "retweeted_tweet", None))
                is_quote = bool(getattr(t, "is_quote_status", False))
                created_at = getattr(t, "created_at", "") or ""

                # Extract media urls
                media_urls: list[str] = []
                media_list = getattr(t, "media", []) or []
                for m in media_list:
                    m_url = getattr(m, "media_url_https", None) or getattr(m, "url", None)
                    if m_url:
                        media_urls.append(m_url)

                if not media_urls:
                    legacy_media = getattr(t, "_legacy", {}).get("entities", {}).get("media", [])
                    for m in legacy_media:
                        if isinstance(m, dict) and m.get("media_url_https"):
                            media_urls.append(m["media_url_https"])

                parsed_list.append(
                    TweetData(
                        id=tweet_id,
                        text=text,
                        author_handle=author,
                        is_reply=is_reply,
                        is_retweet=is_retweet,
                        is_quote=is_quote,
                        created_at=created_at,
                        media=media_urls,
                    )
                )
            except Exception as parse_err:
                logger.debug("Skipping unparseable tweet object: %s", parse_err)

        return parsed_list

    def _handle_twikit_error(self, exc: Exception, is_during_login: bool = False) -> None:
        """Map twikit-specific exceptions into typed domain exceptions."""
        from twikit import errors

        if isinstance(exc, errors.TooManyRequests):
            raise RateLimitException("X rate limit exceeded (HTTP 429).") from exc
        elif isinstance(exc, (errors.AccountLocked, errors.Forbidden)):
            raise AccountLockedException("Data account is locked, challenged, or captcha required.") from exc
        elif isinstance(exc, errors.AccountSuspended):
            raise AccountSuspendedException("Data account has been suspended.") from exc
        elif isinstance(exc, errors.Unauthorized):
            raise SessionExpiredException("X session/cookie is unauthorized or expired.") from exc
        elif isinstance(exc, (errors.RequestTimeout, errors.ServerError, TimeoutError)):
            raise NetworkException(f"Network / timeout error communicating with X: {exc}") from exc
        else:
            raise FetcherException(f"X Fetcher encountered error: {exc}") from exc

    async def close(self) -> None:
        """Clean up twikit client resources."""
        self.client = None
