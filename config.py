"""Configuration schema and loading for NotifyMe application."""

import os
import yaml
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class TelegramConfig:
    """Telegram Bot and Chat destination settings."""
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
    auth_token: str = ""
    ct0: str = ""


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
    """Global and per-account filtering rules."""
    include_replies: bool = False
    include_retweets: bool = False
    include_quotes: bool = False
    keyword_allowlist: list[str] = field(default_factory=list)
    keyword_blocklist: list[str] = field(default_factory=list)
    account_overrides: dict[str, AccountOverrideConfig] = field(default_factory=dict)


@dataclass
class AlertConfig:
    """Health alerts and failure thresholds."""
    max_consecutive_failures: int = 5
    inactivity_alert_minutes: int = 10
    alert_cooldown_minutes: int = 30


@dataclass
class WebConfig:
    """Desktop Web UI server configuration."""
    host: str = "127.0.0.1"
    port: int = 8080


@dataclass
class StorageConfig:
    """SQLite persistence settings."""
    db_path: str = "data/notifyme.db"


@dataclass
class AppConfig:
    """Root configuration holding all sub-components."""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    x_account: XAccountConfig = field(default_factory=XAccountConfig)
    poll: PollConfig = field(default_factory=PollConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    web: WebConfig = field(default_factory=WebConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)


def load_config(config_path: str = "config.yaml", env_file: str = ".env") -> AppConfig:
    """Load configuration prioritizing environment variables over YAML defaults."""
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)

    raw_yaml: dict = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                raw_yaml = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Error parsing {config_path}: {exc}") from exc

    tg_raw = raw_yaml.get("telegram", {})
    x_raw = raw_yaml.get("x_account", {})
    poll_raw = raw_yaml.get("poll", {})
    filters_raw = raw_yaml.get("filters", {})
    alerts_raw = raw_yaml.get("alerts", {})
    web_raw = raw_yaml.get("web", {})
    storage_raw = raw_yaml.get("storage", {})

    # Account overrides parsing
    raw_overrides = filters_raw.get("account_overrides", {})
    parsed_overrides: dict[str, AccountOverrideConfig] = {}
    for handle, rules in raw_overrides.items():
        if isinstance(rules, dict):
            parsed_overrides[handle.lower()] = AccountOverrideConfig(
                include_replies=rules.get("include_replies"),
                include_retweets=rules.get("include_retweets"),
                include_quotes=rules.get("include_quotes"),
                keyword_allowlist=rules.get("keyword_allowlist"),
                keyword_blocklist=rules.get("keyword_blocklist"),
            )

    return AppConfig(
        telegram=TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", tg_raw.get("bot_token", "")),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", tg_raw.get("chat_id", "")),
            alert_chat_id=os.getenv("TELEGRAM_ALERT_CHAT_ID", tg_raw.get("alert_chat_id", "")),
        ),
        x_account=XAccountConfig(
            username=os.getenv("X_USERNAME", x_raw.get("username", "")),
            email=os.getenv("X_EMAIL", x_raw.get("email", "")),
            password=os.getenv("X_PASSWORD", x_raw.get("password", "")),
            totp_secret=os.getenv("X_TOTP_SECRET", x_raw.get("totp_secret", "")),
            list_id=os.getenv("X_LIST_ID", str(x_raw.get("list_id", ""))),
            cookies_path=os.getenv("X_COOKIES_PATH", x_raw.get("cookies_path", "data/cookies.json")),
            auth_token=os.getenv("X_AUTH_TOKEN", x_raw.get("auth_token", "")),
            ct0=os.getenv("X_CT0", x_raw.get("ct0", "")),
        ),
        poll=PollConfig(
            interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", poll_raw.get("interval_seconds", 60))),
            jitter_max_seconds=int(os.getenv("POLL_JITTER_MAX_SECONDS", poll_raw.get("jitter_max_seconds", 10))),
        ),
        filters=FilterConfig(
            include_replies=bool(filters_raw.get("include_replies", False)),
            include_retweets=bool(filters_raw.get("include_retweets", False)),
            include_quotes=bool(filters_raw.get("include_quotes", False)),
            keyword_allowlist=list(filters_raw.get("keyword_allowlist", [])),
            keyword_blocklist=list(filters_raw.get("keyword_blocklist", [])),
            account_overrides=parsed_overrides,
        ),
        alerts=AlertConfig(
            max_consecutive_failures=int(alerts_raw.get("max_consecutive_failures", 5)),
            inactivity_alert_minutes=int(alerts_raw.get("inactivity_alert_minutes", 10)),
            alert_cooldown_minutes=int(alerts_raw.get("alert_cooldown_minutes", 30)),
        ),
        web=WebConfig(
            host=os.getenv("WEB_HOST", web_raw.get("host", "127.0.0.1")),
            port=int(os.getenv("WEB_PORT", web_raw.get("port", 8080))),
        ),
        storage=StorageConfig(
            db_path=os.getenv("DB_PATH", storage_raw.get("db_path", "data/notifyme.db")),
        ),
    )
