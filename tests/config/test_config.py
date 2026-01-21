"""統合Config クラスのテスト"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from slack_feed_enricher.config import Config, load_config


class TestConfig:
    """Configクラスのテスト"""

    def test_config_has_all_fields(self) -> None:
        """Configが全フィールドを持つこと"""
        config = Config(
            slack_bot_token="xoxb-test",
            rss_feed_channel_id="C0123456789",
            polling_interval=600,
            message_limit=10,
        )
        assert config.slack_bot_token == "xoxb-test"
        assert config.rss_feed_channel_id == "C0123456789"
        assert config.polling_interval == 600
        assert config.message_limit == 10

    def test_config_has_default_values(self) -> None:
        """Configがデフォルト値を持つこと"""
        config = Config(
            slack_bot_token="xoxb-test",
            rss_feed_channel_id="C0123456789",
        )
        assert config.polling_interval == 600
        assert config.message_limit == 10


class TestLoadConfig:
    """load_config関数のテスト"""

    def test_load_config_from_env_and_yaml(self, tmp_path: Path) -> None:
        """環境変数とYAMLファイルから設定を読み込むこと"""
        # YAMLファイルを作成
        config_file = tmp_path / "config.yaml"
        config_file.write_text("polling_interval: 300\nmessage_limit: 20\n")

        test_env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "RSS_FEED_CHANNEL_ID": "C9876543210",
        }

        with patch.dict(os.environ, test_env, clear=False):
            config = load_config(config_file)

        assert config.slack_bot_token == "xoxb-test-token"
        assert config.rss_feed_channel_id == "C9876543210"
        assert config.polling_interval == 300
        assert config.message_limit == 20

    def test_load_config_with_empty_yaml_fails(self, tmp_path: Path) -> None:
        """YAMLファイルが空の場合にエラーになること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        test_env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "RSS_FEED_CHANNEL_ID": "C9876543210",
        }

        with patch.dict(os.environ, test_env, clear=False), pytest.raises(ValueError, match="Config file is empty"):
            load_config(config_file)

    def test_load_config_fails_when_env_missing(self, tmp_path: Path) -> None:
        """環境変数が欠けている場合にエラーになること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="Required environment variable is missing"):
            load_config(config_file)

    def test_load_config_fails_when_yaml_not_found(self) -> None:
        """YAMLファイルが存在しない場合にエラーになること"""
        test_env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "RSS_FEED_CHANNEL_ID": "C9876543210",
        }

        with patch.dict(os.environ, test_env, clear=False), pytest.raises(FileNotFoundError):
            load_config(Path("nonexistent.yaml"))
