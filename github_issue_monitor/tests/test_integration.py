import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from github_issue_monitor.models import RelevanceCategory
from github_issue_monitor.storage import IssueStorage
from github_issue_monitor.fetcher import FetchResult, RateLimited, FetchError
from github_issue_monitor.config import MonitorConfig
from github_issue_monitor.main import run_cycle


@pytest.fixture
def base_config(tmp_path):
    return MonitorConfig(
        repos=["open-telemetry/opentelemetry-collector-contrib"],
        interval_minutes=15,
        max_age_hours=24,
        max_alerts_per_cycle=10,
        ignore_users={"dependabot[bot]"},
        db_path=str(tmp_path / "integration_issues.db"),
    )


@pytest.mark.asyncio
async def test_first_run_baselines_and_gives_zero_alerts(base_config):
    storage = IssueStorage(base_config.db_path)
    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_issue = AsyncMock(return_value=True)

    fake_issues = [
        {
            "number": 1,
            "title": "Existing Bug",
            "state": "open",
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
            "comments": 0,
            "assignees": [],
            "user": {"login": "dev1"},
            "html_url": "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/1",
        }
    ]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=fake_issues, etag='W/"etag1"'))

    # Run cycle
    alert_count = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)

    assert alert_count == 0
    mock_notifier.send_issue.assert_not_called()
    assert storage.is_baselined("open-telemetry/opentelemetry-collector-contrib")
    assert storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 1)
    assert storage.get_etag("open-telemetry/opentelemetry-collector-contrib") == 'W/"etag1"'


@pytest.mark.asyncio
async def test_mixed_batch_filters_and_sends_one_alert(base_config):
    storage = IssueStorage(base_config.db_path)
    # Pre-baseline repo
    storage.set_baselined("open-telemetry/opentelemetry-collector-contrib")

    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_issue = AsyncMock(return_value=True)

    fake_issues = [
        # PR: rejected
        {
            "number": 10,
            "title": "PR to fix",
            "state": "open",
            "pull_request": {"url": "..."},
            "user": {"login": "dev1"},
            "created_at": "2026-11-15T00:00:00Z",
        },
        # Bot: rejected
        {
            "number": 11,
            "title": "Bump dep",
            "state": "open",
            "user": {"login": "dependabot[bot]"},
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
        },
        # Assigned: rejected
        {
            "number": 12,
            "title": "Crash in exporter",
            "state": "open",
            "assignees": [{"login": "someone"}],
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
        },
        # Relevant bug: accepted!
        {
            "number": 13,
            "title": "Crash in processor",
            "state": "open",
            "comments": 0,
            "assignees": [],
            "user": {"login": "user-contributor"},
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/13",
        },
    ]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=fake_issues, etag='W/"etag2"'))

    alert_count = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count == 1
    assert mock_notifier.send_issue.call_count == 1
    assert storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 13)


@pytest.mark.asyncio
async def test_second_cycle_gives_zero_alerts(base_config):
    storage = IssueStorage(base_config.db_path)
    storage.set_baselined("open-telemetry/opentelemetry-collector-contrib")
    storage.mark_seen("open-telemetry/opentelemetry-collector-contrib", 13)

    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_issue = AsyncMock(return_value=True)

    fake_issues = [
        {
            "number": 13,
            "title": "Crash in processor",
            "state": "open",
            "comments": 0,
            "assignees": [],
            "user": {"login": "user-contributor"},
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
        }
    ]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=fake_issues, etag='W/"etag2"'))

    alert_count = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count == 0
    mock_notifier.send_issue.assert_not_called()


@pytest.mark.asyncio
async def test_failed_send_retries_next_cycle(base_config):
    storage = IssueStorage(base_config.db_path)
    storage.set_baselined("open-telemetry/opentelemetry-collector-contrib")

    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    # Send fails
    mock_notifier.send_issue = AsyncMock(return_value=False)

    fake_issues = [
        {
            "number": 20,
            "title": "New issue",
            "state": "open",
            "comments": 0,
            "assignees": [],
            "user": {"login": "user1"},
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/20",
        }
    ]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=fake_issues, etag='W/"etag_fail"'))

    # First cycle fails
    alert_count1 = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count1 == 0
    # Must NOT be marked as seen
    assert not storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 20)
    # ETag must NOT be saved when send fails
    assert storage.get_etag("open-telemetry/opentelemetry-collector-contrib") is None

    # Next cycle send succeeds
    mock_notifier.send_issue = AsyncMock(return_value=True)
    alert_count2 = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count2 == 1
    assert storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 20)
    assert storage.get_etag("open-telemetry/opentelemetry-collector-contrib") == 'W/"etag_fail"'


@pytest.mark.asyncio
async def test_late_label_arrival_notified(base_config):
    storage = IssueStorage(base_config.db_path)
    storage.set_baselined("open-telemetry/opentelemetry-collector-contrib")

    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_issue = AsyncMock(return_value=True)

    # In cycle 1, issue has no labels (not relevant)
    fake_issue = {
        "number": 30,
        "title": "Random question",
        "state": "open",
        "comments": 0,
        "assignees": [],
        "user": {"login": "user1"},
        "created_at": "2026-11-15T00:00:00Z",
        "labels": [],
        "html_url": "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/30",
    }
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=[fake_issue], etag='W/"etag_a"'))

    alert_count1 = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count1 == 0
    # Crucial: Not marked seen if not relevant
    assert not storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 30)

    # In cycle 2, label is added late
    fake_issue["labels"] = [{"name": "bug"}]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=[fake_issue], etag='W/"etag_b"'))

    alert_count2 = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count2 == 1
    assert storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 30)


@pytest.mark.asyncio
async def test_dry_run_leaves_database_empty(base_config):
    storage = IssueStorage(base_config.db_path)
    storage.set_baselined("open-telemetry/opentelemetry-collector-contrib")

    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_issue = AsyncMock(return_value=True)

    fake_issues = [
        {
            "number": 40,
            "title": "Dry run issue",
            "state": "open",
            "comments": 0,
            "assignees": [],
            "user": {"login": "user1"},
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/40",
        }
    ]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=fake_issues, etag='W/"etag_dry"'))

    # Run with dry_run=True
    alert_count = await run_cycle(base_config, storage, mock_fetcher, mock_notifier, dry_run=True)
    assert alert_count == 1
    # Notifier must NOT send
    mock_notifier.send_issue.assert_not_called()
    # Database must remain empty
    assert not storage.is_seen("open-telemetry/opentelemetry-collector-contrib", 40)
    assert storage.get_etag("open-telemetry/opentelemetry-collector-contrib") is None


@pytest.mark.asyncio
async def test_max_alerts_per_cycle_limit_and_summary(base_config):
    storage = IssueStorage(base_config.db_path)
    storage.set_baselined("open-telemetry/opentelemetry-collector-contrib")

    mock_fetcher = MagicMock()
    mock_notifier = MagicMock()
    mock_notifier.send_issue = AsyncMock(return_value=True)
    mock_notifier.send_message = AsyncMock(return_value=True)

    # 15 relevant issues, cap is 10
    fake_issues = [
        {
            "number": i,
            "title": f"Issue #{i}",
            "state": "open",
            "comments": 0,
            "assignees": [],
            "user": {"login": f"user{i}"},
            "created_at": "2026-11-15T00:00:00Z",
            "labels": [{"name": "bug"}],
            "html_url": f"https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/{i}",
        }
        for i in range(1, 16)
    ]
    mock_fetcher.fetch = AsyncMock(return_value=FetchResult(status="ok", issues=fake_issues, etag='W/"etag_cap"'))

    alert_count = await run_cycle(base_config, storage, mock_fetcher, mock_notifier)
    assert alert_count == 10
    assert mock_notifier.send_issue.call_count == 10
    # Summary notification sent for overflow
    assert mock_notifier.send_message.call_count == 1
