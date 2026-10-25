"""Embedded asynchronous web server for the native local desktop interface."""

from __future__ import annotations
import os
import time
import logging
from aiohttp import web
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from main import MonitorEngine

logger = logging.getLogger("notifyme.web")


class WebDashboard:
    """Provides a local HTTP server and REST endpoints for the desktop HTML/CSS dashboard."""

    def __init__(self, engine: MonitorEngine, host: str = "127.0.0.1", port: int = 8080):
        self.engine = engine
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/api/status", self.handle_api_status)
        self.app.router.add_post("/api/pause", self.handle_api_pause)
        self.app.router.add_post("/api/resume", self.handle_api_resume)
        self.app.router.add_post("/api/poll_now", self.handle_api_poll_now)

        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_dir):
            self.app.router.add_static("/static/", path=static_dir, name="static")

    async def handle_index(self, request: web.Request) -> web.Response:
        """Serve the native HTML desktop dashboard."""
        html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            return web.Response(text=content, content_type="text/html")
        return web.Response(text="<h1>NotifyMe Dashboard</h1><p>Static UI files missing.</p>", content_type="text/html")

    async def handle_api_status(self, request: web.Request) -> web.Response:
        """Return live telemetry and recent tweet notifications."""
        stats = self.engine.storage.get_stats()
        recent_tweets = self.engine.storage.get_recent_notified(limit=30)
        recent_polls = self.engine.storage.get_recent_polls(limit=15)

        uptime = time.time() - self.engine.start_time
        data = {
            "status": "paused" if self.engine.is_paused else ("error" if self.engine.consecutive_failures > 0 else "running"),
            "is_paused": self.engine.is_paused,
            "uptime_seconds": int(uptime),
            "consecutive_failures": self.engine.consecutive_failures,
            "list_id": self.engine.config.x_account.list_id,
            "poll_interval": self.engine.config.poll.interval_seconds,
            "stats": stats,
            "recent_tweets": recent_tweets,
            "recent_polls": recent_polls,
            "filter_settings": {
                "include_replies": self.engine.config.filters.include_replies,
                "include_retweets": self.engine.config.filters.include_retweets,
                "include_quotes": self.engine.config.filters.include_quotes,
                "allowlist_count": len(self.engine.config.filters.keyword_allowlist),
                "blocklist_count": len(self.engine.config.filters.keyword_blocklist),
            },
        }
        return web.json_response(data)

    async def handle_api_pause(self, request: web.Request) -> web.Response:
        """Pause polling loop."""
        self.engine.is_paused = True
        logger.info("Monitor paused via local web dashboard.")
        return web.json_response({"success": True, "is_paused": True})

    async def handle_api_resume(self, request: web.Request) -> web.Response:
        """Resume polling loop."""
        self.engine.is_paused = False
        logger.info("Monitor resumed via local web dashboard.")
        return web.json_response({"success": True, "is_paused": False})

    async def handle_api_poll_now(self, request: web.Request) -> web.Response:
        """Request immediate execution of a polling cycle."""
        logger.info("Manual poll triggered via local web dashboard.")
        self.engine.trigger_immediate_poll()
        return web.json_response({"success": True, "message": "Poll triggered"})

    async def start(self) -> None:
        """Start local web server asynchronously."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info("Desktop HTML/CSS Dashboard available at http://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop local web server."""
        if self.runner:
            await self.runner.cleanup()
