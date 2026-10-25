"""X (Twitter) List timeline fetcher interface and implementation.

Adheres to Clean Architecture boundaries by defining a BaseFetcher interface
so that TwikitFetcher can be swapped with the official Twitter API client without
modifying business logic.
"""

from abc import ABC, abstractmethod
import logging
import os
from typing import Any
from config import XAccountConfig
from filters import TweetData

logger = logging.getLogger("notifyme.fetcher")


class FetcherException(Exception):
    """Base exception for all fetching operations."""
    pass


class RateLimitException(FetcherException):
    """Raised when X API returns HTTP 429 Too Many Requests."""
    pass


class AccountLockedException(FetcherException):
    """Raised when data account is locked, challenged, or requires human verification."""
    pass


class AccountSuspendedException(FetcherException):
    """Raised when data account has been suspended by X."""
    pass


class SessionExpiredException(FetcherException):
    """Raised when stored cookies / session has expired or requires re-authentication."""
    pass


class NetworkException(FetcherException):
    """Raised on connection timeouts, DNS failures, or remote server disconnects."""
    pass


class BaseFetcher(ABC):
    """Abstract fetching interface to decouple scraping client from core engine."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize sessions, cookies, or authorization tokens."""
        pass

    @abstractmethod
    async def fetch_list_tweets(self, list_id: str, count: int = 40) -> list[TweetData]:
        """Retrieve recent tweets from a specific list."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Release underlying connections and resources."""
        pass


class TwikitFetcher(BaseFetcher):
    """X List fetcher powered by twikit / twifork unofficial client library."""

    def __init__(self, config: XAccountConfig):
        self.config = config
        self.client: Any = None

    async def initialize(self) -> None:
        """Initialize twikit client and authenticate using saved cookies or direct tokens."""
        from twikit import Client

        self.client = Client(language="en-US")
        cookies_file = self.config.cookies_path

        # 1. Direct auth_token & ct0 from environment / config
        if self.config.auth_token and self.config.ct0:
            logger.info("Using X session cookies configured in environment (auth_token & ct0)")
            cookies_dict = {
                "auth_token": self.config.auth_token,
                "ct0": self.config.ct0,
            }
            self.client.set_cookies(cookies_dict)
            if cookies_file:
                try:
                    os.makedirs(os.path.dirname(cookies_file) or ".", exist_ok=True)
                    self.client.save_cookies(cookies_file)
                except Exception as save_err:
                    logger.debug("Could not cache cookies to %s: %s", cookies_file, save_err)
            return

        # 2. Existing cookies file on disk
        if cookies_file and os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 10:
            try:
                logger.info("Loading existing X session from %s", cookies_file)
                self.client.load_cookies(cookies_file)
                return
            except Exception as exc:
                logger.warning("Failed to load existing cookies from %s: %s. Attempting fresh login...", cookies_file, exc)

        # 3. Attempt programmatic login if credentials exist
        if self.config.username and self.config.password:
            await self._login_and_save_cookies()
            return

        # 4. No cookies and no credentials
        raise SessionExpiredException(
            "X authentication required. Please provide X_AUTH_TOKEN and X_CT0 in your .env file, "
            "or run 'python setup_cookies.py' to save your browser cookies into data/cookies.json."
        )

    async def _login_and_save_cookies(self) -> None:
        """Execute a login and persist cookies to disk."""
        if not self.config.username or not self.config.password:
            raise SessionExpiredException(
                "X credentials not provided. Set X_AUTH_TOKEN and X_CT0 in .env, or run 'python setup_cookies.py'."
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
            from twikit import errors
            err_msg = str(exc)
            if (
                isinstance(exc, getattr(errors, "LoginRetired", ()))
                or "LoginRetired" in type(exc).__name__
                or "LoginFlow" in err_msg
                or "KEY_BYTE" in err_msg
                or "ClientTransaction" in err_msg
            ):
                raise SessionExpiredException(
                    "X has retired programmatic username/password logins for HTTP clients (requires in-browser $castle_token). "
                    "Please provide session cookies: set X_AUTH_TOKEN and X_CT0 in .env or run 'python setup_cookies.py'."
                ) from exc
            self._handle_twikit_error(exc, is_during_login=True)

    async def fetch_list_tweets(self, list_id: str, count: int = 40) -> list[TweetData]:
        """Fetch the latest tweets from the specified X List timeline."""
        if not self.client:
            await self.initialize()

        try:
            raw_tweets = await self.client.get_list_tweets(list_id=str(list_id), count=count)
        except Exception as exc:
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
        if not raw_tweets:
            return parsed_list

        for t in raw_tweets:
            try:
                tweet_id = int(t.id)
                full_text = getattr(t, "full_text", None) or getattr(t, "text", "") or ""
                author_handle = getattr(t.user, "screen_name", "") or ""
                is_reply = bool(getattr(t, "in_reply_to", None))
                is_retweet = bool(getattr(t, "retweeted_tweet", None))
                is_quote = bool(getattr(t, "is_quote_status", False))
                created_at = getattr(t, "created_at", "") or ""

                media_urls: list[str] = []
                raw_media = getattr(t, "media", None) or []
                for m in raw_media:
                    media_url = getattr(m, "media_url_https", None) or getattr(m, "url", None)
                    if media_url:
                        media_urls.append(str(media_url))

                parsed_list.append(
                    TweetData(
                        id=tweet_id,
                        text=full_text,
                        author_handle=author_handle,
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

        err_name = type(exc).__name__
        err_msg = str(exc)

        if isinstance(exc, errors.TooManyRequests):
            raise RateLimitException("X rate limit exceeded (HTTP 429).") from exc
        elif isinstance(exc, (errors.AccountLocked, errors.Forbidden)):
            raise AccountLockedException("Data account is locked, challenged, or captcha required.") from exc
        elif isinstance(exc, errors.AccountSuspended):
            raise AccountSuspendedException("Data account has been suspended.") from exc
        elif isinstance(exc, (errors.Unauthorized, getattr(errors, "InvalidSession", ()))):
            raise SessionExpiredException("X session/cookie is unauthorized or expired.") from exc
        elif (
            isinstance(exc, getattr(errors, "LoginRetired", ()))
            or "LoginRetired" in err_name
            or "LoginFlow" in err_msg
            or "KEY_BYTE" in err_msg
            or "ClientTransaction" in err_msg
        ):
            raise SessionExpiredException(
                "X has retired programmatic username/password logins for HTTP clients. "
                "Please provide session cookies: set X_AUTH_TOKEN and X_CT0 in .env or run 'python setup_cookies.py'."
            ) from exc
        elif isinstance(exc, (errors.RequestTimeout, errors.ServerError, TimeoutError)):
            raise NetworkException(f"Network / timeout error communicating with X: {exc}") from exc
        else:
            raise FetcherException(f"X Fetcher encountered error: {exc}") from exc

    async def close(self) -> None:
        """Clean up twikit client resources."""
        self.client = None
