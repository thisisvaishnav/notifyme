"""Configuration loader for GitHub Issue Monitor."""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
from github_issue_monitor.models import RelevanceCategory


@dataclass
class MonitorConfig:
    repos: list[str] = field(default_factory=lambda: ["open-telemetry/opentelemetry-collector-contrib"])
    interval_minutes: int = 15
    max_age_hours: int = 24
    max_alerts_per_cycle: int = 10
    ignore_users: set[str] = field(default_factory=lambda: {"dependabot[bot]", "renovate[bot]", "codecov[bot]", "github-actions[bot]"})
    bug_labels: set[str] = field(default_factory=lambda: {"bug", "defect", "kind/bug", "type/bug"})
    enhancement_labels: set[str] = field(default_factory=lambda: {"enhancement", "feature", "kind/enhancement", "type/feature"})
    help_wanted_labels: set[str] = field(default_factory=lambda: {"help wanted", "good first issue", "good-first-issue", "help-wanted"})
    keywords: dict[str, RelevanceCategory] = field(default_factory=dict)
    db_path: str = "github_issue_monitor/data/issues.db"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    github_token: str = ""


def _load_env_file(dotenv_path: Path) -> None:
    """Simple parser for .env files without requiring python-dotenv."""
    if not dotenv_path.is_file():
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


def load_config(config_path: str | Path | None = None) -> MonitorConfig:
    """Load configuration from YAML file and environment variables."""
    # Look for .env in github_issue_monitor/ and repo root
    _load_env_file(Path("github_issue_monitor/.env"))
    _load_env_file(Path(".env"))

    if config_path is None:
        config_path = Path("github_issue_monitor/config.yaml")
    else:
        config_path = Path(config_path)

    raw_cfg: dict[str, Any] = {}
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                raw_cfg = loaded

    repos = raw_cfg.get("repos") or ["open-telemetry/opentelemetry-collector-contrib"]
    interval_minutes = int(raw_cfg.get("interval_minutes", 15))
    max_age_hours = int(raw_cfg.get("max_age_hours", 24))
    max_alerts_per_cycle = int(raw_cfg.get("max_alerts_per_cycle", 10))

    ignore_users_raw = raw_cfg.get("ignore_users") or []
    ignore_users = {str(u).strip().lower() for u in ignore_users_raw}

    labels_cfg = raw_cfg.get("labels") or {}
    bug_labels = {str(l).strip().lower() for l in labels_cfg.get("bug", ["bug", "defect", "kind/bug", "type/bug"])}
    enhancement_labels = {str(l).strip().lower() for l in labels_cfg.get("enhancement", ["enhancement", "feature"])}
    help_wanted_labels = {str(l).strip().lower() for l in labels_cfg.get("help_wanted", ["help wanted", "good first issue"])}

    keywords_raw = raw_cfg.get("keywords") or {}
    keywords: dict[str, RelevanceCategory] = {}
    for kw, cat_name in keywords_raw.items():
        try:
            keywords[kw] = RelevanceCategory[str(cat_name).upper()]
        except KeyError:
            keywords[kw] = RelevanceCategory.BUG

    db_path = str(raw_cfg.get("db_path", "github_issue_monitor/data/issues.db"))

    telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()

    return MonitorConfig(
        repos=repos,
        interval_minutes=interval_minutes,
        max_age_hours=max_age_hours,
        max_alerts_per_cycle=max_alerts_per_cycle,
        ignore_users=ignore_users,
        bug_labels=bug_labels,
        enhancement_labels=enhancement_labels,
        help_wanted_labels=help_wanted_labels,
        keywords=keywords,
        db_path=db_path,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        github_token=github_token,
    )
