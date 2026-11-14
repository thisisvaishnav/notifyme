"""Telegram notification delivery for GitHub Issue alerts."""

from __future__ import annotations
import html
import logging
import asyncio
from typing import Any
import aiohttp
from github_issue_monitor.models import IssueData

logger = logging.getLogger("github_issue_monitor.notifier")


def _mask_token(token: str) -> str:
    """Mask token string for safe logging."""
    if not token or len(token) < 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def format_telegram_issue_message(issue: IssueData, reply: str) -> str:
    """Format an IssueData and ASD-STE100 reply into a safe Telegram HTML message.

    Constraints:
    - Only <b>, <code>, <a> permitted.
    - Reply enclosed in a single <code> block for 1-tap copy on mobile.
    - Escapes XML characters (&, <, >) and quotes in URLs.
    - Truncates title to ensure total message length is <= 4096 characters.
    """
    escaped_repo = html.escape(issue.repo)
    escaped_author = html.escape(issue.author) if issue.author else "unknown"
    author_str = f"@{escaped_author}" if issue.author else "unknown"
    labels_str = ", ".join(issue.labels) if issue.labels else "none"
    escaped_labels = html.escape(labels_str)
    escaped_url = html.escape(issue.url, quote=True)
    escaped_reply = html.escape(reply)

    # Base template structure without title
    header = f"🐙 <b>{escaped_repo} #{issue.number}</b>\n📌 "
    middle = f"\n👤 {author_str} | 🏷️ {escaped_labels}\n🔗 <a href=\"{escaped_url}\">{escaped_url}</a>\n\n💬 Tap to copy reply:\n<code>{escaped_reply}</code>"

    # Telegram hard limit is 4096 chars. Leave safety margin.
    max_total_len = 4090
    fixed_len = len(header) + len(middle)

    available_for_title = max_total_len - fixed_len

    title_text = issue.title
    if len(title_text) > available_for_title:
        title_text = title_text[: max(0, available_for_title - 3)] + "..."

    escaped_title = html.escape(title_text)

    # In case escaping expanded the title beyond limit, trim further
    while len(header) + len(escaped_title) + len(middle) > max_total_len and len(title_text) > 4:
        title_text = title_text[:-4] + "..."
        escaped_title = html.escape(title_text)

    return f"{header}{escaped_title}{middle}"


class TelegramIssueNotifier:
    """Delivers issue alerts to Telegram Bot API with rate-limit retries."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        session: aiohttp.ClientSession | None = None,
    ):
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id).strip()
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
            self._owns_session = True
        elif getattr(self._session, "closed", False) is True:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._owns_session and self._session and getattr(self._session, "closed", False) is not True:
            await self._session.close()

    async def send_message(self, text: str) -> bool:
        """Send raw HTML message to configured chat."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram bot_token or chat_id not configured; skipping notification.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        session = await self._get_session()
        masked = _mask_token(self.bot_token)

        for attempt in range(3):
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True

                    if resp.status == 429:
                        try:
                            data = await resp.json()
                            retry_after = float(data.get("parameters", {}).get("retry_after", 1.0))
                        except Exception:
                            retry_after = 1.0

                        logger.warning(
                            "Telegram rate limited (429) using bot [%s]. Retrying after %.1fs (attempt %d/3)",
                            masked,
                            retry_after,
                            attempt + 1,
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    err_body = await resp.text()
                    logger.error(
                        "Telegram sendMessage failed with HTTP %d for bot [%s]: %s",
                        resp.status,
                        masked,
                        err_body,
                    )
                    return False

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Network error sending Telegram message with bot [%s]: %s",
                    masked,
                    exc,
                )
                return False

        return False

    async def send_issue(self, issue: IssueData, reply: str) -> bool:
        """Send formatted issue alert to configured chat."""
        message = format_telegram_issue_message(issue, reply)
        return await self.send_message(message)
