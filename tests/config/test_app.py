from pathlib import Path

import pytest
import yaml

from slack_feed_enricher.config.app import AppConfig, load_app_config


class TestAppConfig:
    """AppConfig Pydanticモデルのテスト"""

    def test_valid_app_config(self) -> None:
        """正常な設定でAppConfigが作成できること"""
        config = AppConfig(
            polling_interval=600,
            message_limit=10,
        )
        assert config.polling_interval == 600
        assert config.message_limit == 10

    def test_default_values(self) -> None:
        """デフォルト値が正しく設定されること"""
        config = AppConfig()
        assert config.polling_interval == 600
        assert config.message_limit == 10

    def test_custom_values(self) -> None:
        """カスタム値が正しく設定されること"""
        config = AppConfig(
            polling_interval=300,
            message_limit=20,
        )
        assert config.polling_interval == 300
        assert config.message_limit == 20

    def test_reject_unknown_fields(self) -> None:
        """未知のフィールドでエラーになること"""
        with pytest.raises(ValueError):
            AppConfig(unknown_field="value")  # type: ignore[call-arg]


class TestLoadAppConfig:
    """load_app_config関数のテスト"""

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        """YAMLファイルから正しく読み込めること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump({
                "polling_interval": 300,
                "message_limit": 20,
            })
        )

        config = load_app_config(config_file)
        assert config.polling_interval == 300
        assert config.message_limit == 20

    def test_load_with_default_values(self, tmp_path: Path) -> None:
        """一部の値のみ指定した場合、デフォルト値が使われること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump({
                "polling_interval": 300,
            })
        )

        config = load_app_config(config_file)
        assert config.polling_interval == 300
        assert config.message_limit == 10  # デフォルト値

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        """空のYAMLファイルの場合にエラーになること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        with pytest.raises(ValueError, match="Config file is empty"):
            load_app_config(config_file)

    def test_load_fails_when_file_not_exists(self) -> None:
        """ファイルが存在しない場合にエラーになること"""
        with pytest.raises(FileNotFoundError):
            load_app_config(Path("/nonexistent/config.yaml"))

    def test_load_fails_when_invalid_yaml(self, tmp_path: Path) -> None:
        """不正なYAMLの場合にエラーになること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content:")

        with pytest.raises(ValueError):
            load_app_config(config_file)

    def test_reject_unknown_fields_in_yaml(self, tmp_path: Path) -> None:
        """YAMLに未知のフィールドがある場合にエラーになること"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump({
                "polling_interval": 300,
                "unknown_field": "value",
            })
        )

        with pytest.raises(ValueError):
            load_app_config(config_file)
