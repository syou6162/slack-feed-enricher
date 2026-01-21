import os
from unittest.mock import patch

import pytest

from slack_feed_enricher.config.env import EnvConfig, load_env_config


class TestEnvConfig:
    """EnvConfig Pydanticモデルのテスト"""

    def test_valid_env_config(self) -> None:
        """正常な環境変数でEnvConfigが作成できること"""
        config = EnvConfig(
            slack_bot_token="xoxb-test-token",
            rss_feed_channel_id="C0123456789",
        )
        assert config.slack_bot_token == "xoxb-test-token"
        assert config.rss_feed_channel_id == "C0123456789"

    def test_missing_slack_bot_token(self) -> None:
        """SLACK_BOT_TOKENが欠けている場合にエラーになること"""
        with pytest.raises(ValueError):
            EnvConfig(rss_feed_channel_id="C0123456789")

    def test_missing_rss_feed_channel_id(self) -> None:
        """RSS_FEED_CHANNEL_IDが欠けている場合にエラーになること"""
        with pytest.raises(ValueError):
            EnvConfig(slack_bot_token="xoxb-test-token")


class TestLoadEnvConfig:
    """load_env_config関数のテスト"""

    def test_load_from_environment_variables(self) -> None:
        """環境変数から正しく読み込めること"""
        with patch.dict(
            os.environ,
            {
                "SLACK_BOT_TOKEN": "xoxb-env-token",
                "RSS_FEED_CHANNEL_ID": "C9876543210",
            },
        ):
            config = load_env_config()
            assert config.slack_bot_token == "xoxb-env-token"
            assert config.rss_feed_channel_id == "C9876543210"

    def test_load_fails_when_missing_env_vars(self) -> None:
        """必須環境変数が欠けている場合にエラーになること"""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError):
            load_env_config()
