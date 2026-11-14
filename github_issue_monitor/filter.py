"""Pure relevance classification filter for GitHub Issues."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from github_issue_monitor.models import RelevanceCategory


@dataclass
class FilterRules:
    """Configurable rules for relevance classification."""
    ignore_users: set[str] = field(default_factory=set)
    keywords: dict[str, RelevanceCategory] = field(default_factory=dict)
    bug_labels: set[str] = field(default_factory=lambda: {"bug", "defect", "kind/bug", "type/bug"})
    enhancement_labels: set[str] = field(default_factory=lambda: {"enhancement", "feature", "kind/enhancement", "type/feature"})
    help_wanted_labels: set[str] = field(default_factory=lambda: {"help wanted", "good first issue", "good-first-issue", "help-wanted"})


def classify_issue(raw: dict[str, Any], rules: FilterRules) -> tuple[bool, RelevanceCategory | None, str]:
    """Pure function classifying a raw GitHub API issue payload.

    Returns:
        (is_relevant, category, reason)
    """
    # 1. Reject Pull Requests
    if "pull_request" in raw and raw["pull_request"]:
        return False, None, "Rejected: Contains pull_request key"

    # 2. Reject non-open states
    state = str(raw.get("state", "")).lower()
    if state != "open":
        return False, None, f"Rejected: Issue state is '{state}' (not open)"

    # 3. Reject locked issues
    if raw.get("locked"):
        return False, None, "Rejected: Issue is locked"

    # 4. Reject assigned issues
    assignees = raw.get("assignees") or []
    if assignees:
        return False, None, f"Rejected: Issue has {len(assignees)} assignee(s)"

    # 5. Reject issues that already have comments
    comments = int(raw.get("comments", 0))
    if comments > 0:
        return False, None, f"Rejected: Issue already has {comments} comment(s)"

    # 6. Reject bots and ignored users
    user_info = raw.get("user") or {}
    user_type = str(user_info.get("type", "")).lower()
    if user_type == "bot":
        return False, None, "Rejected: User type is Bot"

    login = str(user_info.get("login", "")).strip().lower()
    if login.endswith("[bot]"):
        return False, None, f"Rejected: User '{login}' ends with [bot]"

    normalized_ignored = {u.strip().lower() for u in rules.ignore_users}
    if login in normalized_ignored:
        return False, None, f"Rejected: User '{login}' is in ignored users list"

    # Extract label names
    raw_labels = raw.get("labels") or []
    labels: list[str] = []
    for item in raw_labels:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                labels.append(str(name).strip().lower())
        elif isinstance(item, str):
            labels.append(item.strip().lower())

    label_set = set(labels)

    # Category matching order:
    # First: Bug label
    for bug_lbl in rules.bug_labels:
        if bug_lbl.lower() in label_set:
            return True, RelevanceCategory.BUG, f"Matched bug label: '{bug_lbl}'"

    # Second: Enhancement label
    for enh_lbl in rules.enhancement_labels:
        if enh_lbl.lower() in label_set:
            return True, RelevanceCategory.ENHANCEMENT, f"Matched enhancement label: '{enh_lbl}'"

    # Third: Help wanted / Good first issue label
    for hw_lbl in rules.help_wanted_labels:
        if hw_lbl.lower() in label_set:
            return True, RelevanceCategory.HELP_WANTED, f"Matched help wanted label: '{hw_lbl}'"

    # Fourth: Keyword match in title or body
    title = str(raw.get("title", "")).lower()
    body = str(raw.get("body", "")).lower()
    text = f"{title} {body}"

    for kw, cat in rules.keywords.items():
        if kw.lower() in text:
            return True, cat, f"Matched keyword: '{kw}' -> {cat.value}"

    return False, None, "Rejected: Not relevant (no matching labels or keywords)"
