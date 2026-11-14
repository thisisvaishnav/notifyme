import pytest
import html
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from github_issue_monitor.models import IssueData
from github_issue_monitor.notifier import format_telegram_issue_message, TelegramIssueNotifier


@pytest.fixture
def sample_issue():
    return IssueData(
        repo="open-telemetry/opentelemetry-collector-contrib",
        number=1234,
        title="Crash when parsing <script>&\"alert()\"</script>",
        author="alice<bad>",
        url="https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/1234?a=1&b=2",
        labels=["bug", "good first issue"],
        created_at="2026-11-15T00:00:00Z",
        body="Some body text",
    )


def test_format_escapes_xml_and_quotes(sample_issue):
    reply = "Hello @alice. I will investigate this defect & fix it."
    msg = format_telegram_issue_message(sample_issue, reply)

    # Must contain escaped strings
    assert "&lt;script&gt;&amp;&quot;alert()&quot;&lt;/script&gt;" in msg
    assert "alice&lt;bad&gt;" in msg
    assert "&amp; fix it." in msg
    assert html.escape(sample_issue.url, quote=True) in msg

    # Only permitted Telegram tags: <b>, <code>, <a>
    # No unescaped <script>
    assert "<script>" not in msg

    # Reply must be wrapped in <code>...</code>
    assert f"<code>{html.escape(reply)}</code>" in msg


def test_format_message_under_4096_cuts_title_first():
    long_title = "A" * 5000
    issue = IssueData(
        repo="open-telemetry/opentelemetry-collector-contrib",
        number=1,
        title=long_title,
        author="alice",
        url="https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/1",
        labels=["bug"],
    )
    reply = "Hello @alice. I will investigate this defect. Assign this issue to me."
    msg = format_telegram_issue_message(issue, reply)

    assert len(msg) <= 4096
    assert "..." in msg
    # Reply code block must be fully preserved
    assert f"<code>{html.escape(reply)}</code>" in msg


@pytest.mark.asyncio
async def test_notifier_send_success(sample_issue):
    fake_response = AsyncMock()
    fake_response.status = 200
    fake_response.json = AsyncMock(return_value={"ok": True})
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.closed = False
    session.post = MagicMock(return_value=fake_response)

    notifier = TelegramIssueNotifier(
        bot_token="123456:SECRET_TOKEN_ABC",
        chat_id="999999",
        session=session,
    )
    result = await notifier.send_issue(sample_issue, "Hello @alice. Assign this issue to me.")
    assert result is True
    session.post.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_429_retry_and_success(sample_issue):
    resp_429 = AsyncMock()
    resp_429.status = 429
    resp_429.json = AsyncMock(return_value={"parameters": {"retry_after": 0.01}})
    resp_429.__aenter__ = AsyncMock(return_value=resp_429)
    resp_429.__aexit__ = AsyncMock(return_value=None)

    resp_200 = AsyncMock()
    resp_200.status = 200
    resp_200.json = AsyncMock(return_value={"ok": True})
    resp_200.__aenter__ = AsyncMock(return_value=resp_200)
    resp_200.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.closed = False
    session.post = MagicMock(side_effect=[resp_429, resp_200])

    notifier = TelegramIssueNotifier(
        bot_token="123456:SECRET_TOKEN_ABC",
        chat_id="999999",
        session=session,
    )
    result = await notifier.send_issue(sample_issue, "Hello @alice.")
    assert result is True
    assert session.post.call_count == 2


@pytest.mark.asyncio
async def test_notifier_error_returns_false(sample_issue):
    resp_500 = AsyncMock()
    resp_500.status = 500
    resp_500.text = AsyncMock(return_value="Server error")
    resp_500.__aenter__ = AsyncMock(return_value=resp_500)
    resp_500.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.closed = False
    session.post = MagicMock(return_value=resp_500)

    notifier = TelegramIssueNotifier(
        bot_token="123456:SECRET_TOKEN_ABC",
        chat_id="999999",
        session=session,
    )
    result = await notifier.send_issue(sample_issue, "Hello @alice.")
    assert result is False


@pytest.mark.asyncio
async def test_logs_never_leak_bot_token(caplog, sample_issue):
    token = "SECRET_TOKEN_12345XYZ"
    resp_500 = AsyncMock()
    resp_500.status = 500
    resp_500.text = AsyncMock(return_value="Internal error")
    resp_500.__aenter__ = AsyncMock(return_value=resp_500)
    resp_500.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.closed = False
    session.post = MagicMock(return_value=resp_500)

    notifier = TelegramIssueNotifier(
        bot_token=token,
        chat_id="999999",
        session=session,
    )
    with caplog.at_level(logging.DEBUG):
        await notifier.send_issue(sample_issue, "Hello.")

    for record in caplog.records:
        assert token not in record.message
        assert token not in str(record)
