import pytest
from github_issue_monitor.models import RelevanceCategory
from github_issue_monitor.filter import FilterRules, classify_issue


@pytest.fixture
def default_rules():
    return FilterRules(
        ignore_users={"dependabot", "renovate", "codecov"},
        keywords={"crash": RelevanceCategory.BUG, "proposal": RelevanceCategory.ENHANCEMENT},
    )


def test_reject_pull_request(default_rules):
    raw = {
        "number": 1,
        "title": "Fix crash",
        "state": "open",
        "pull_request": {"url": "https://api.github.com/repos/org/repo/pulls/1"},
        "user": {"login": "dev", "type": "User"},
        "assignees": [],
        "comments": 0,
        "locked": False,
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert cat is None
    assert "pull_request" in reason.lower()


def test_reject_closed_issue(default_rules):
    raw = {
        "number": 2,
        "title": "Fix crash",
        "state": "closed",
        "user": {"login": "dev", "type": "User"},
        "assignees": [],
        "comments": 0,
        "locked": False,
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "closed" in reason.lower() or "state" in reason.lower()


def test_reject_locked_issue(default_rules):
    raw = {
        "number": 3,
        "title": "Fix crash",
        "state": "open",
        "locked": True,
        "user": {"login": "dev", "type": "User"},
        "assignees": [],
        "comments": 0,
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "locked" in reason.lower()


def test_reject_assigned_issue(default_rules):
    raw = {
        "number": 4,
        "title": "Fix crash",
        "state": "open",
        "locked": False,
        "assignees": [{"login": "someone"}],
        "comments": 0,
        "user": {"login": "dev", "type": "User"},
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "assignee" in reason.lower()


def test_reject_issue_with_comments(default_rules):
    raw = {
        "number": 5,
        "title": "Fix crash",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 2,
        "user": {"login": "dev", "type": "User"},
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "comment" in reason.lower()


def test_reject_user_type_bot(default_rules):
    raw = {
        "number": 6,
        "title": "Fix crash",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "my-service", "type": "Bot"},
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "bot" in reason.lower()


def test_reject_user_ending_with_bot(default_rules):
    raw = {
        "number": 7,
        "title": "Fix crash",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "github-actions[bot]", "type": "User"},
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "bot" in reason.lower()


def test_reject_user_in_ignore_users(default_rules):
    raw = {
        "number": 8,
        "title": "Fix crash",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "dependabot", "type": "User"},
        "labels": [{"name": "bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert "ignored user" in reason.lower() or "ignore" in reason.lower()


def test_category_bug_label(default_rules):
    raw = {
        "number": 9,
        "title": "Unexpected nil pointer",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [{"name": "Bug"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert is_rel
    assert cat == RelevanceCategory.BUG


def test_category_enhancement_label(default_rules):
    raw = {
        "number": 10,
        "title": "Add gRPC stream metrics",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [{"name": "Enhancement"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert is_rel
    assert cat == RelevanceCategory.ENHANCEMENT


def test_category_help_wanted_label(default_rules):
    raw = {
        "number": 11,
        "title": "Refactor exporter package",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [{"name": "Help Wanted"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert is_rel
    assert cat == RelevanceCategory.HELP_WANTED


def test_category_good_first_issue_label(default_rules):
    raw = {
        "number": 12,
        "title": "Clean up error string formatting",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [{"name": "Good First Issue"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert is_rel
    assert cat == RelevanceCategory.HELP_WANTED


def test_category_keyword_match(default_rules):
    raw = {
        "number": 13,
        "title": "Collector crash on startup",
        "body": "System panics with nil pointer",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert is_rel
    assert cat == RelevanceCategory.BUG


def test_no_match_not_relevant(default_rules):
    raw = {
        "number": 14,
        "title": "General discussion topic",
        "body": "Just asking general questions",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [{"name": "question"}],
    }
    is_rel, cat, reason = classify_issue(raw, default_rules)
    assert not is_rel
    assert cat is None
    assert "not relevant" in reason.lower()


def test_late_label_arrival(default_rules):
    # Initially no labels, not relevant
    raw = {
        "number": 15,
        "title": "Update parser",
        "body": "Some details",
        "state": "open",
        "locked": False,
        "assignees": [],
        "comments": 0,
        "user": {"login": "developer", "type": "User"},
        "labels": [],
    }
    is_rel1, cat1, _ = classify_issue(raw, default_rules)
    assert not is_rel1

    # Now label arrives late
    raw["labels"] = [{"name": "bug"}]
    is_rel2, cat2, _ = classify_issue(raw, default_rules)
    assert is_rel2
    assert cat2 == RelevanceCategory.BUG
