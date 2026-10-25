"""Unit tests for the embedded desktop web dashboard endpoints."""

import pytest
import tempfile
import os
from aiohttp.test_utils import AioHTTPTestCase
from web import WebDashboard
from storage import SQLiteStorage
from config import AppConfig, XAccountConfig, PollConfig
from main import MonitorEngine
from unittest.mock import AsyncMock


class WebDashboardTestCase(AioHTTPTestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    async def get_application(self):
        storage = SQLiteStorage(self.temp_db.name)
        storage.initialize()
        storage.set_baseline(12345)
        storage.mark_tweet_notified(
            tweet_id=12345,
            author_handle="test_guy",
            text="Test tweet for dashboard",
            created_at="now",
            media_urls=[],
        )

        config = AppConfig(
            x_account=XAccountConfig(list_id="5544332211"),
            poll=PollConfig(interval_seconds=60),
        )

        mock_fetcher = AsyncMock()
        mock_notifier = AsyncMock()
        engine = MonitorEngine(config, storage, mock_fetcher, mock_notifier)

        dashboard = WebDashboard(engine, host="127.0.0.1", port=8080)
        return dashboard.app

    async def test_get_status_api(self):
        resp = await self.client.request("GET", "/api/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["list_id"] == "5544332211"
        assert data["is_paused"] is False
        assert len(data["recent_tweets"]) == 1
        assert data["recent_tweets"][0]["author_handle"] == "test_guy"

    async def test_pause_and_resume_api(self):
        # Pause
        resp = await self.client.request("POST", "/api/pause")
        assert resp.status == 200
        data = await resp.json()
        assert data["is_paused"] is True

        # Check status reflects pause
        resp_status = await self.client.request("GET", "/api/status")
        data_status = await resp_status.json()
        assert data_status["is_paused"] is True
        assert data_status["status"] == "paused"

        # Resume
        resp_resume = await self.client.request("POST", "/api/resume")
        assert resp_resume.status == 200
        data_resume = await resp_resume.json()
        assert data_resume["is_paused"] is False

    async def test_poll_now_api(self):
        resp = await self.client.request("POST", "/api/poll_now")
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True

    async def test_index_page(self):
        resp = await self.client.request("GET", "/")
        assert resp.status == 200
        text = await resp.text()
        assert "NotifyMe" in text
