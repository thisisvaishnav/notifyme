"""Telegram Bot notification client with safe HTML escaping and alert cooldowns."""

from __future__ import annotations
import html
import time
from datetime import datetime, timezone
import logging
import asyncio
import aiohttp
from typing import Any
from config import TelegramConfig, AlertConfig
from filters import TweetData

logger = logging.getLogger("notifyme.notifier")


def format_tweet_timestamp(created_at_str: str) -> str:
    """Format tweet created_at string into HH:MM UTC if possible, or return original if short."""
    if not created_at_str:
        return ""
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(created_at_str, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%H:%M UTC")
        except (ValueError, TypeError):
            continue
    if len(created_at_str) <= 15:
        return created_at_str
    return ""


class TelegramNotifier:
    """Sends notifications, digest summaries, and health alerts to Telegram using the Bot API."""

    def __init__(self, telegram_config: TelegramConfig, alert_config: AlertConfig):
        self.tg_config = telegram_config
        self.alert_config = alert_config
        self.api_url = f"https://api.telegram.org/bot{self.tg_config.bot_token}/sendMessage"
        self._alert_timestamps: dict[str, float] = {}
        self._active_alerts: set[str] = set()
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close client HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def format_tweet_message(self, tweet: TweetData) -> str:
        """Format a TweetData object into safe Telegram HTML markup within character limits."""
        escaped_handle = html.escape(tweet.author_handle)
        escaped_url = html.escape(tweet.url, quote=True)
        escaped_created = html.escape(tweet.created_at)

        media_hint = ""
        if tweet.media:
            count = len(tweet.media)
            media_hint = f"\n📷/🎬 <i>Attached Media: {count} item{'s' if count > 1 else ''}</i>"

        header = f"🐦 <b><a href=\"https://x.com/{escaped_handle}\">@{escaped_handle}</a></b> posted:\n\n"
        footer = f"{media_hint}\n\n🔗 <a href=\"{escaped_url}\">View on X</a>\n🕒 <code>{escaped_created}</code>"

        # Calculate max allowable text length (Telegram limit is 4096)
        overhead_len = len(header) + len(footer)
        max_text_len = 4096 - overhead_len - 10  # 10 char safety buffer

        raw_text = tweet.text
        if len(raw_text) > max_text_len:
            raw_text = raw_text[: max_text_len - 3] + "..."

        escaped_text = html.escape(raw_text)
        return f"{header}{escaped_text}{footer}"

    def format_posts_digest(self, tweets: list[TweetData], window_label: str = "10m") -> list[str]:
        """Format a batch of TweetData into grouped card-style Telegram HTML messages (Option 3).

        Args:
            tweets: List of TweetData objects to format.
            window_label: Cadence label for header (e.g. '10m').

        Returns:
            List of Telegram-compatible HTML formatted message chunks (<= 4096 chars each).
        """
        if not tweets:
            return []

        # Group tweets by author_handle preserving order of appearance
        grouped: dict[str, list[TweetData]] = {}
        for t in tweets:
            grouped.setdefault(t.author_handle, []).append(t)

        header = f"🔔 <b>New Posts Summary ({window_label})</b>\n\n"
        messages: list[str] = []
        current_content = header

        for handle, user_tweets in grouped.items():
            escaped_handle = html.escape(handle)
            count = len(user_tweets)
            post_label = "post" if count == 1 else "posts"
            user_block = f"👤 <b><a href=\"https://x.com/{escaped_handle}\">@{escaped_handle}</a></b> ({count} {post_label}):\n"

            item_lines = []
            for idx, tweet in enumerate(user_tweets, start=1):
                raw_text = " ".join(tweet.text.split()) if tweet.text else ""
                if len(raw_text) > 200:
                    raw_text = raw_text[:197] + "..."

                if raw_text:
                    escaped_text = f'"{html.escape(raw_text)}"'
                elif tweet.media:
                    escaped_text = "<i>(Media only)</i>"
                else:
                    escaped_text = "<i>(No text)</i>"

                display_url = tweet.url.replace("https://", "").replace("http://", "")
                escaped_display_url = html.escape(display_url)
                escaped_url = html.escape(tweet.url, quote=True)

                time_str = format_tweet_timestamp(tweet.created_at)
                time_part = f" • <code>{html.escape(time_str)}</code>" if time_str else ""

                media_part = ""
                if tweet.media:
                    m_len = len(tweet.media)
                    m_label = "item" if m_len == 1 else "items"
                    media_part = f"\n   📷 <i>Attached Media: {m_len} {m_label}</i>"

                item_lines.append(
                    f'{idx}. {escaped_text}\n'
                    f'   🔗 <a href="{escaped_url}">{escaped_display_url}</a>{time_part}{media_part}'
                )

            user_block += "\n".join(item_lines) + "\n\n"

            # Check if adding this user_block would exceed limit (Telegram max is 4096)
            if len(current_content) + len(user_block) > 3800:
                if current_content.strip() != header.strip():
                    messages.append(current_content.strip())
                    current_content = header + user_block
                else:
                    messages.append((current_content + user_block).strip())
                    current_content = header
            else:
                current_content += user_block

        if current_content.strip() and current_content.strip() != header.strip():
            messages.append(current_content.strip())

        return messages

    async def send_tweet_notification(self, tweet: TweetData) -> bool:
        """Deliver a formatted single tweet to the target Telegram chat."""
        if not self.tg_config.bot_token or not self.tg_config.chat_id:
            logger.warning("Telegram bot_token or chat_id is not configured; skipping notification.")
            return False

        message = self.format_tweet_message(tweet)
        return await self._send_raw_message(self.tg_config.chat_id, message)

    async def send_posts_digest(self, tweets: list[TweetData], window_label: str = "10m") -> bool:
        """Deliver a batch of new posts grouped by author in a summary digest to Telegram."""
        if not tweets:
            return True

        if not self.tg_config.bot_token or not self.tg_config.chat_id:
            logger.warning("Telegram bot_token or chat_id is not configured; skipping summary.")
            return False

        messages = self.format_posts_digest(tweets, window_label=window_label)
        all_sent = True
        for msg in messages:
            sent = await self._send_raw_message(self.tg_config.chat_id, msg, disable_web_page_preview=True)
            if not sent:
                all_sent = False
                break
            await asyncio.sleep(0.5)

        return all_sent

    async def send_message(self, message: str, chat_id: str | None = None) -> bool:
        """Send a general HTML formatted message to the configured Telegram chat."""
        target_chat = chat_id or self.tg_config.chat_id
        if not self.tg_config.bot_token or not target_chat:
            logger.warning("Telegram bot_token or chat_id is not configured; skipping message.")
            return False
        return await self._send_raw_message(target_chat, message)

    def can_send_alert(self, alert_type: str) -> bool:
        """Check if an alert type is past its cooldown period."""
        last_time = self._alert_timestamps.get(alert_type, 0.0)
        cooldown_sec = self.alert_config.alert_cooldown_minutes * 60
        return (time.time() - last_time) >= cooldown_sec

    def record_alert_sent(self, alert_type: str) -> None:
        """Record the timestamp of an alert."""
        self._alert_timestamps[alert_type] = time.time()
        self._active_alerts.add(alert_type)

    async def send_alert(self, alert_type: str, message: str) -> bool:
        """Send an urgent operational alert if cooldown allows."""
        if not self.can_send_alert(alert_type):
            logger.info("Alert '%s' suppressed by cooldown (sent within %s min)", alert_type, self.alert_config.alert_cooldown_minutes)
            return False

        target_chat = self.tg_config.alert_chat_id or self.tg_config.chat_id
        if not self.tg_config.bot_token or not target_chat:
            logger.warning("Telegram credentials missing; cannot send alert '%s'", alert_type)
            return False

        formatted_alert = (
            f"🚨 <b>X MONITOR ALERT</b>\n\n"
            f"<b>Type:</b> <code>{html.escape(alert_type)}</code>\n"
            f"<b>Details:</b> {html.escape(message)}\n\n"
            f"🕒 <code>{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</code>"
        )

        success = await self._send_raw_message(target_chat, formatted_alert)
        if success:
            self.record_alert_sent(alert_type)
        return success

    async def send_recovery_alert(self, alert_type: str, message: str) -> bool:
        """Send a recovery notification if an alert was previously active."""
        if alert_type not in self._active_alerts:
            return False

        target_chat = self.tg_config.alert_chat_id or self.tg_config.chat_id
        formatted_recovery = (
            f"✅ <b>X MONITOR RECOVERED</b>\n\n"
            f"<b>Resolved:</b> <code>{html.escape(alert_type)}</code>\n"
            f"<b>Status:</b> {html.escape(message)}\n\n"
            f"🕒 <code>{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</code>"
        )
        success = await self._send_raw_message(target_chat, formatted_recovery)
        if success:
            self._active_alerts.discard(alert_type)
        return success

    async def _send_raw_message(self, chat_id: str, html_text: str, disable_web_page_preview: bool = False) -> bool:
        """Execute the HTTP POST request to Telegram API with retry on 429."""
        session = await self._get_session()
        payload = {
            "chat_id": chat_id,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with session.post(self.api_url, json=payload) as resp:
                    if resp.status == 200:
                        return True

                    resp_data: dict[str, Any] = {}
                    try:
                        resp_data = await resp.json()
                    except Exception:
                        pass

                    if resp.status == 429:
                        retry_after = resp_data.get("parameters", {}).get("retry_after", 3)
                        logger.warning("Telegram rate limited (429). Retrying after %s seconds...", retry_after)
                        if attempt < max_retries:
                            await asyncio.sleep(retry_after)
                            continue

                    logger.error("Failed to send Telegram message. HTTP %s: %s", resp.status, resp_data)
                    return False
            except asyncio.TimeoutError:
                logger.error("Telegram API request timed out (attempt %d/%d)", attempt + 1, max_retries + 1)
            except Exception as exc:
                logger.error("Telegram API unexpected exception: %s", exc)

        return False
