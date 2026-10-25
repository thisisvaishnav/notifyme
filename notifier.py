"""Telegram Bot notification client with safe HTML escaping and alert cooldowns."""

from __future__ import annotations
import html
import time
import logging
import asyncio
import aiohttp
from typing import Any
from config import TelegramConfig, AlertConfig
from filters import TweetData

logger = logging.getLogger("notifyme.notifier")


class TelegramNotifier:
    """Sends notifications and health alerts to Telegram using the Bot API."""

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

    async def send_tweet_notification(self, tweet: TweetData) -> bool:
        """Deliver a formatted tweet to the target Telegram chat."""
        if not self.tg_config.bot_token or not self.tg_config.chat_id:
            logger.warning("Telegram bot_token or chat_id is not configured; skipping notification.")
            return False

        message = self.format_tweet_message(tweet)
        return await self._send_raw_message(self.tg_config.chat_id, message)

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

    async def _send_raw_message(self, chat_id: str, html_text: str) -> bool:
        """Execute the HTTP POST request to Telegram API with retry on 429."""
        session = await self._get_session()
        payload = {
            "chat_id": chat_id,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
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
