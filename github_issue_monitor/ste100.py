"""ASD-STE100 (Simplified Technical English) first-response generator."""

from __future__ import annotations
import re
from github_issue_monitor.models import IssueData, RelevanceCategory

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,39}$")


def _format_greeting(author: str) -> str:
    """Format greeting with optional validated GitHub username mention."""
    if author and USERNAME_PATTERN.match(author):
        return f"Hello @{author}."
    return "Hello."


def generate_ste100_reply(issue: IssueData, category: RelevanceCategory) -> str:
    """Generate an ASD-STE100 compliant draft first response.

    Rules strictly enforced:
    - Maximum 20 words per sentence.
    - No contractions (don't, can't, it's).
    - No prohibited polite/ambiguous words (please, just, should, could, etc.).
    - Never falsely claims the defect is reproduced or fixed.
    - Uses active, direct instructions.
    """
    greeting = _format_greeting(issue.author)

    if category == RelevanceCategory.BUG:
        return (
            f"{greeting} I will investigate this defect. "
            f"I will prepare a fix for this issue. "
            f"Assign this issue to me."
        )

    if category == RelevanceCategory.ENHANCEMENT:
        return (
            f"{greeting} I will review the requirements for this enhancement. "
            f"I want to implement this change. "
            f"Assign this issue to me."
        )

    if category == RelevanceCategory.HELP_WANTED:
        return (
            f"{greeting} I want to work on this issue. "
            f"I will review the codebase and submit a pull request. "
            f"Assign this issue to me."
        )

    if category == RelevanceCategory.QUESTION:
        return (
            f"{greeting} Can you provide the logs or configuration details for this behavior? "
            f"I will test this scenario."
        )

    # Fallback default
    return (
        f"{greeting} I want to work on this issue. "
        f"Assign this issue to me."
    )
