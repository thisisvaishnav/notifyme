import re
import pytest
from github_issue_monitor.models import IssueData, RelevanceCategory, parse_issue
from github_issue_monitor.ste100 import generate_ste100_reply


def test_parse_issue_creates_issue_data():
    raw = {
        "number": 101,
        "title": "Collector crash in receiver",
        "html_url": "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/101",
        "user": {"login": "dev-user"},
        "labels": [{"name": "bug"}, {"name": "help wanted"}],
        "created_at": "2026-11-15T00:00:00Z",
        "body": "The receiver crashes when parsing nil payload.",
        "comments": 0,
        "state": "open",
        "locked": False,
        "assignees": [],
    }
    issue = parse_issue(raw, "open-telemetry/opentelemetry-collector-contrib")
    assert issue.repo == "open-telemetry/opentelemetry-collector-contrib"
    assert issue.number == 101
    assert issue.title == "Collector crash in receiver"
    assert issue.author == "dev-user"
    assert issue.url == "https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/101"
    assert "bug" in issue.labels


@pytest.mark.parametrize("category", [
    RelevanceCategory.BUG,
    RelevanceCategory.ENHANCEMENT,
    RelevanceCategory.HELP_WANTED,
    RelevanceCategory.QUESTION,
])
def test_all_categories_give_non_empty_reply(category):
    issue = IssueData(
        repo="open-telemetry/opentelemetry-collector-contrib",
        number=101,
        title="Collector issue",
        author="alice",
        url="https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/101",
        labels=["bug"],
        created_at="2026-11-15T00:00:00Z",
        body="Sample description",
    )
    reply = generate_ste100_reply(issue, category)
    assert reply
    assert isinstance(reply, str)
    assert len(reply.strip()) > 0


@pytest.mark.parametrize("category", [
    RelevanceCategory.BUG,
    RelevanceCategory.ENHANCEMENT,
    RelevanceCategory.HELP_WANTED,
    RelevanceCategory.QUESTION,
])
def test_sentence_length_and_ste100_rules(category):
    issue = IssueData(
        repo="open-telemetry/opentelemetry-collector-contrib",
        number=101,
        title="Collector issue with receiver component",
        author="alice",
        url="https://github.com/open-telemetry/opentelemetry-collector-contrib/issues/101",
        labels=["bug"],
        created_at="2026-11-15T00:00:00Z",
        body="Sample description",
    )
    reply = generate_ste100_reply(issue, category)

    # 1. Check max words per sentence (<= 20 words per ASD-STE100)
    # Split sentences by period, exclamation, or question mark
    sentences = [s.strip() for s in re.split(r"[.!?]\s*", reply) if s.strip()]
    for s in sentences:
        words = s.split()
        assert len(words) <= 20, f"Sentence exceeds 20 words ({len(words)} words): '{s}'"

    # 2. Check no contractions (don't, can't, it's, etc.)
    contractions = ["don't", "can't", "it's", "i'm", "won't", "shouldn't", "wouldn't", "couldn't", "haven't", "hasn't"]
    for c in contractions:
        assert c not in reply.lower(), f"Reply contains contraction '{c}': '{reply}'"

    # 3. Check no banned words (please, just, should, etc.)
    banned_words = [r"\bplease\b", r"\bjust\b", r"\bshould\b", r"\bcould\b", r"\bmight\b", r"\bmaybe\b"]
    for b in banned_words:
        assert not re.search(b, reply, re.IGNORECASE), f"Reply contains banned word matching '{b}': '{reply}'"

    # 4. Check never claims that bug is reproduced or fixed
    assert "i reproduced" not in reply.lower()
    assert "i have reproduced" not in reply.lower()
    assert "fixed this" not in reply.lower()
    assert "i fixed" not in reply.lower()


def test_username_validation_and_mention():
    valid_author = "alice-123"
    issue_valid = IssueData(
        repo="test/repo",
        number=1,
        title="Test issue",
        author=valid_author,
        url="https://github.com/test/repo/issues/1",
        labels=[],
        created_at="2026-11-15T00:00:00Z",
        body="",
    )
    reply_valid = generate_ste100_reply(issue_valid, RelevanceCategory.BUG)
    assert f"@{valid_author}" in reply_valid

    # Invalid usernames (e.g. spaces, special characters, >39 chars, or empty)
    invalid_author = "bad user!@#"
    issue_invalid = IssueData(
        repo="test/repo",
        number=2,
        title="Test issue",
        author=invalid_author,
        url="https://github.com/test/repo/issues/2",
        labels=[],
        created_at="2026-11-15T00:00:00Z",
        body="",
    )
    reply_invalid = generate_ste100_reply(issue_invalid, RelevanceCategory.BUG)
    assert "@" not in reply_invalid
