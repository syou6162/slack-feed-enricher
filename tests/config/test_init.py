"""config/__init__.pyの統合テスト"""

from slack_feed_enricher.config import AppConfig, EnvConfig, load_app_config, load_env_config


def test_can_import_env_config() -> None:
    """EnvConfigをインポートできること"""
    assert EnvConfig is not None


def test_can_import_app_config() -> None:
    """AppConfigをインポートできること"""
    assert AppConfig is not None


def test_can_import_load_env_config() -> None:
    """load_env_configをインポートできること"""
    assert load_env_config is not None


def test_can_import_load_app_config() -> None:
    """load_app_configをインポートできること"""
    assert load_app_config is not None
