"""GitHub Issues API fetcher with ETag conditional caching and rate limit handling."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any, Literal
import aiohttp


class FetchError(Exception):
    """Raised when GitHub API request fails due to server error, network issue, or timeout."""
    pass


class RateLimited(Exception):
    """Raised when GitHub API rate limits are exhausted."""
    def __init__(self, reset_at: int = 0, retry_after: int | None = None):
        super().__init__(f"GitHub API rate limit exceeded (reset_at: {reset_at}, retry_after: {retry_after})")
        self.reset_at = reset_at
        self.retry_after = retry_after


@dataclass
class FetchResult:
    """Result of fetching issues for a repository."""
    status: Literal["ok", "not_modified"]
    issues: list[dict[str, Any]]
    etag: str | None


class GitHubIssueFetcher:
    """Fetches open issues from GitHub REST API respecting conditional ETag headers."""

    def __init__(self, session: aiohttp.ClientSession, token: str | None = None):
        self.session = session
        self.token = token.strip() if (token and token.strip()) else None

    async def fetch(self, repo: str, etag: str | None = None) -> FetchResult:
        """Fetch latest open issues for given repository.

        Args:
            repo: 'owner/repo' string (e.g. 'open-telemetry/opentelemetry-collector-contrib')
            etag: Optional HTTP ETag from previous fetch.

        Returns:
            FetchResult with status 'ok' or 'not_modified'.
        """
        url = f"https://api.github.com/repos/{repo}/issues"
        params = {
            "state": "open",
            "sort": "created",
            "direction": "desc",
            "per_page": 100,
        }
        headers = {
            "User-Agent": "github-issue-monitor/1.0",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if etag:
            headers["If-None-Match"] = etag.strip()

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        timeout = aiohttp.ClientTimeout(total=20)

        try:
            async with self.session.get(url, params=params, headers=headers, timeout=timeout) as resp:
                if resp.status == 304:
                    return FetchResult(status="not_modified", issues=[], etag=etag)

                if resp.status in (403, 429):
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    reset_header = resp.headers.get("X-RateLimit-Reset")
                    retry_header = resp.headers.get("Retry-After")

                    reset_at = int(reset_header) if (reset_header and reset_header.isdigit()) else 0
                    retry_after = int(retry_header) if (retry_header and retry_header.isdigit()) else None

                    # If remaining == 0 or status 429, handle as rate limited
                    if resp.status == 429 or remaining == "0":
                        raise RateLimited(reset_at=reset_at, retry_after=retry_after)

                    error_text = await resp.text()
                    raise FetchError(f"GitHub API 403 Forbidden: {error_text}")

                if resp.status == 200:
                    new_etag = resp.headers.get("ETag") or etag
                    issues_data = await resp.json()
                    return FetchResult(status="ok", issues=issues_data, etag=new_etag)

                error_text = await resp.text()
                raise FetchError(f"GitHub API HTTP {resp.status}: {error_text}")

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise FetchError(f"Network error or timeout fetching issues for {repo}: {exc}") from exc
