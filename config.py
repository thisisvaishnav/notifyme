"""Configuration loader and schema definitions for X Account Monitor."""

from __future__ import annotations
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


@dataclass
class TelegramConfig:
    """Telegram bot configuration settings."""
    bot_token: str = ""
    chat_id: str = ""
    alert_chat_id: str = ""

    def __post_init__(self):
        if not self.alert_chat_id and self.chat_id:
            self.alert_chat_id = self.chat_id


@dataclass
class XAccountConfig:
    """X / Twitter account credentials and target List settings."""
    username: str = ""
    email: str = ""
    password: str = ""
    totp_secret: str = ""
    list_id: str = ""
    cookies_path: str = "data/cookies.json"


@dataclass
class PollConfig:
    """Polling interval and jitter timing."""
    interval_seconds: int = 60
    jitter_max_seconds: int = 10


@dataclass
class AccountOverrideConfig:
    """Per-account filtering overrides."""
    include_replies: bool | None = None
    include_retweets: bool | None = None
    include_quotes: bool | None = None
    keyword_allowlist: list[str] | None = None
    keyword_blocklist: list[str] | None = None


@dataclass
class FilterConfig:
    """Global tweet filtering rules."""
    include_replies: bool = False
    include_retweets: bool = False
    include_quotes: bool = False
    keyword_allowlist: list[str] = field(default_factory=list)
    keyword_blocklist: list[str] = field(default_factory=list)
    account_overrides: dict[str, AccountOverrideConfig] = field(default_factory=dict)


@dataclass
class AlertConfig:
    """Alert thresholds and cooldown configuration."""
    max_consecutive_failures: int = 5
    inactivity_alert_minutes: int = 10
    alert_cooldown_minutes: int = 30


@dataclass
class WebConfig:
    """Local HTML/CSS desktop interface configuration."""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass
class StorageConfig:
    """SQLite persistence settings."""
    db_path: str = "data/monitor.db"


@dataclass
class AppConfig:
    """Root application configuration."""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    x_account: XAccountConfig = field(default_factory=XAccountConfig)
    poll: PollConfig = field(default_factory=PollConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    web: WebConfig = field(default_factory=WebConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


def load_config(config_path: str = "config.yaml", env_file: str = ".env") -> AppConfig:
    """Load configuration from YAML and environment variables.

    Environment variables take precedence over config.yaml values for sensitive fields.
    """
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    yaml_data: dict = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    # 1. Telegram
    tg_raw = yaml_data.get("telegram", {})
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN") or tg_raw.get("bot_token", "")
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID") or str(tg_raw.get("chat_id", ""))
    tg_alert_chat_id = os.getenv("TELEGRAM_ALERT_CHAT_ID") or str(tg_raw.get("alert_chat_id", ""))
    telegram_cfg = TelegramConfig(
        bot_token=tg_token,
        chat_id=tg_chat_id,
        alert_chat_id=tg_alert_chat_id or tg_chat_id,
    )

    # 2. X Account
    x_raw = yaml_data.get("x_account", {})
    x_username = os.getenv("X_USERNAME") or x_raw.get("username", "")
    x_email = os.getenv("X_EMAIL") or x_raw.get("email", "")
    x_password = os.getenv("X_PASSWORD") or x_raw.get("password", "")
    x_totp = os.getenv("X_TOTP_SECRET") or x_raw.get("totp_secret", "")
    x_list_id = os.getenv("X_LIST_ID") or str(x_raw.get("list_id", ""))
    x_cookies = os.getenv("X_COOKIES_PATH") or x_raw.get("cookies_path", "data/cookies.json")
    x_cfg = XAccountConfig(
        username=x_username,
        email=x_email,
        password=x_password,
        totp_secret=x_totp,
        list_id=x_list_id,
        cookies_path=x_cookies,
    )

    # 3. Poll
    poll_raw = yaml_data.get("poll", {})
    poll_cfg = PollConfig(
        interval_seconds=int(poll_raw.get("interval_seconds", 60)),
        jitter_max_seconds=int(poll_raw.get("jitter_max_seconds", 10)),
    )

    # 4. Filters
    filters_raw = yaml_data.get("filters", {})
    overrides_raw = filters_raw.get("account_overrides", {}) or {}
    overrides_parsed: dict[str, AccountOverrideConfig] = {}
    for handle, o_cfg in overrides_raw.items():
        if isinstance(o_cfg, dict):
            overrides_parsed[handle.lower().lstrip("@")] = AccountOverrideConfig(
                include_replies=o_cfg.get("include_replies"),
                include_retweets=o_cfg.get("include_retweets"),
                include_quotes=o_cfg.get("include_quotes"),
                keyword_allowlist=o_cfg.get("keyword_allowlist"),
                keyword_blocklist=o_cfg.get("keyword_blocklist"),
            )

    filter_cfg = FilterConfig(
        include_replies=bool(filters_raw.get("include_replies", False)),
        include_retweets=bool(filters_raw.get("include_retweets", False)),
        include_quotes=bool(filters_raw.get("include_quotes", False)),
        keyword_allowlist=[str(w).lower() for w in filters_raw.get("keyword_allowlist", []) or []],
        keyword_blocklist=[str(w).lower() for w in filters_raw.get("keyword_blocklist", []) or []],
        account_overrides=overrides_parsed,
    )

    # 5. Alerts
    alerts_raw = yaml_data.get("alerts", {})
    alert_cfg = AlertConfig(
        max_consecutive_failures=int(alerts_raw.get("max_consecutive_failures", 5)),
        inactivity_alert_minutes=int(alerts_raw.get("inactivity_alert_minutes", 10)),
        alert_cooldown_minutes=int(alerts_raw.get("alert_cooldown_minutes", 30)),
    )

    # 6. Web Dashboard
    web_raw = yaml_data.get("web", {})
    web_cfg = WebConfig(
        enabled=bool(web_raw.get("enabled", True)),
        host=str(web_raw.get("host", "127.0.0.1")),
        port=int(web_raw.get("port", 8080)),
    )

    # 7. Storage
    storage_raw = yaml_data.get("storage", {})
    storage_cfg = StorageConfig(
        db_path=str(storage_raw.get("db_path", "data/monitor.db")),
    )

    # Ensure parent directories exist
    Path(x_cfg.cookies_path).parent.mkdir(parents=True, exist_ok=True)
    Path(storage_cfg.db_path).parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        telegram=telegram_cfg,
        x_account=x_cfg,
        poll=poll_cfg,
        filters=filter_cfg,
        alerts=alert_cfg,
        web=web_cfg,
        storage=storage_cfg,
    )
