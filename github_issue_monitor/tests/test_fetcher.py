import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import aiohttp
from github_issue_monitor.fetcher import GitHubIssueFetcher, FetchResult, RateLimited, FetchError


@pytest.mark.asyncio
async def test_fetch_success_200():
    fake_response = AsyncMock()
    fake_response.status = 200
    fake_response.headers = {
        "ETag": 'W/"12345"',
        "Content-Type": "application/json",
    }
    fake_response.json = AsyncMock(return_value=[{"number": 1, "title": "Test Issue"}])

    session = MagicMock()
    session.get = MagicMock(return_value=fake_response)
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=None)

    fetcher = GitHubIssueFetcher(session=session, token="test-token")
    result = await fetcher.fetch("owner/repo", etag='W/"old"')

    assert result.status == "ok"
    assert len(result.issues) == 1
    assert result.issues[0]["number"] == 1
    assert result.etag == 'W/"12345"'

    # Verify headers sent
    session.get.assert_called_once()
    call_args, call_kwargs = session.get.call_args
    headers = call_kwargs["headers"]
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert headers["If-None-Match"] == 'W/"old"'
    assert headers["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_fetch_not_modified_304():
    fake_response = AsyncMock()
    fake_response.status = 304
    fake_response.headers = {"ETag": 'W/"same"'}

    session = MagicMock()
    session.get = MagicMock(return_value=fake_response)
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=None)

    fetcher = GitHubIssueFetcher(session=session)
    result = await fetcher.fetch("owner/repo", etag='W/"same"')

    assert result.status == "not_modified"
    assert result.issues == []
    assert result.etag == 'W/"same"'


@pytest.mark.asyncio
async def test_fetch_rate_limited_403():
    fake_response = AsyncMock()
    fake_response.status = 403
    fake_response.headers = {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1731630000",
    }
    fake_response.text = AsyncMock(return_value="API rate limit exceeded")

    session = MagicMock()
    session.get = MagicMock(return_value=fake_response)
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=None)

    fetcher = GitHubIssueFetcher(session=session)
    with pytest.raises(RateLimited) as exc:
        await fetcher.fetch("owner/repo")

    assert exc.value.reset_at == 1731630000


@pytest.mark.asyncio
async def test_fetch_rate_limited_429():
    fake_response = AsyncMock()
    fake_response.status = 429
    fake_response.headers = {
        "Retry-After": "60",
        "X-RateLimit-Reset": "1731630060",
    }
    fake_response.text = AsyncMock(return_value="Too Many Requests")

    session = MagicMock()
    session.get = MagicMock(return_value=fake_response)
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=None)

    fetcher = GitHubIssueFetcher(session=session)
    with pytest.raises(RateLimited) as exc:
        await fetcher.fetch("owner/repo")

    assert exc.value.retry_after == 60


@pytest.mark.asyncio
async def test_fetch_server_error_500():
    fake_response = AsyncMock()
    fake_response.status = 500
    fake_response.text = AsyncMock(return_value="Internal Server Error")

    session = MagicMock()
    session.get = MagicMock(return_value=fake_response)
    fake_response.__aenter__ = AsyncMock(return_value=fake_response)
    fake_response.__aexit__ = AsyncMock(return_value=None)

    fetcher = GitHubIssueFetcher(session=session)
    with pytest.raises(FetchError):
        await fetcher.fetch("owner/repo")


@pytest.mark.asyncio
async def test_fetch_timeout():
    session = MagicMock()
    session.get = MagicMock(side_effect=asyncio.TimeoutError())

    fetcher = GitHubIssueFetcher(session=session)
    with pytest.raises(FetchError) as exc:
        await fetcher.fetch("owner/repo")

    assert "timeout" in str(exc.value).lower()
