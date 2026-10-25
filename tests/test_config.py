"""Unit tests for configuration loading and validation."""

import os
import tempfile
import yaml
from config import load_config, AppConfig


def test_load_config_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    config_data = {
        "poll": {
            "interval_seconds": 45,
            "jitter_max_seconds": 5,
        },
        "filters": {
            "include_replies": True,
            "include_retweets": False,
            "keyword_allowlist": ["alpha"],
            "account_overrides": {
                "user_special": {
                    "include_retweets": True,
                    "keyword_allowlist": ["beta"],
                }
            },
        },
        "alerts": {
            "max_consecutive_failures": 3,
            "inactivity_alert_minutes": 15,
        },
        "web": {
            "port": 9090,
        },
        "storage": {
            "db_path": str(tmp_path / "custom.db"),
        },
    }

    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    env_content = """
TELEGRAM_BOT_TOKEN=test_token_123
TELEGRAM_CHAT_ID=999888
X_USERNAME=test_user
X_PASSWORD=secret_pass
X_LIST_ID=11223344
"""
    with open(env_file, "w") as f:
        f.write(env_content)

    cfg = load_config(config_path=str(config_file), env_file=str(env_file))

    assert cfg.telegram.bot_token == "test_token_123"
    assert cfg.telegram.chat_id == "999888"
    assert cfg.x_account.username == "test_user"
    assert cfg.x_account.password == "secret_pass"
    assert cfg.x_account.list_id == "11223344"

    assert cfg.poll.interval_seconds == 45
    assert cfg.poll.jitter_max_seconds == 5

    assert cfg.filters.include_replies is True
    assert cfg.filters.include_retweets is False
    assert "alpha" in cfg.filters.keyword_allowlist
    assert "user_special" in cfg.filters.account_overrides
    assert cfg.filters.account_overrides["user_special"].include_retweets is True

    assert cfg.alerts.max_consecutive_failures == 3
    assert cfg.alerts.inactivity_alert_minutes == 15
    assert cfg.web.port == 9090
    assert cfg.storage.db_path == str(tmp_path / "custom.db")
