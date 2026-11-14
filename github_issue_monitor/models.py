"""Data models for GitHub Issue Monitor."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RelevanceCategory(str, Enum):
    BUG = "BUG"
    ENHANCEMENT = "ENHANCEMENT"
    HELP_WANTED = "HELP_WANTED"
    QUESTION = "QUESTION"


@dataclass
class IssueData:
    """Normalized GitHub Issue representation."""
    repo: str
    number: int
    title: str
    author: str
    url: str
    labels: list[str] = field(default_factory=list)
    created_at: str = ""
    body: str = ""


def parse_issue(raw: dict[str, Any], repo: str) -> IssueData:
    """Parse raw GitHub API issue payload into IssueData."""
    number = int(raw.get("number", 0))
    title = str(raw.get("title", "")).strip()
    url = str(raw.get("html_url", "")).strip()

    user_info = raw.get("user") or {}
    author = str(user_info.get("login", "")).strip()

    raw_labels = raw.get("labels") or []
    labels: list[str] = []
    for item in raw_labels:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                labels.append(str(name).strip().lower())
        elif isinstance(item, str):
            labels.append(item.strip().lower())

    created_at = str(raw.get("created_at", "")).strip()
    body = str(raw.get("body") or "")

    return IssueData(
        repo=repo,
        number=number,
        title=title,
        author=author,
        url=url,
        labels=labels,
        created_at=created_at,
        body=body,
    )
