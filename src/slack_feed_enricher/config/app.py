"""アプリケーション設定"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    """アプリケーション設定"""

    polling_interval: int = Field(default=600, description="ポーリング間隔（秒）")
    message_limit: int = Field(default=10, description="取得メッセージ数")

    model_config = {"extra": "forbid"}


def load_app_config(config_path: Path) -> AppConfig:
    """YAMLファイルからAppConfigを読み込む

    Args:
        config_path: 設定ファイルのパス

    Returns:
        AppConfig: アプリケーション設定

    Raises:
        FileNotFoundError: 設定ファイルが存在しない場合
        ValueError: YAMLファイルが不正な場合
        ValidationError: 設定値が不正な場合
    """
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    try:
        with config_path.open() as f:
            data = yaml.safe_load(f)
            if data is None:
                msg = f"Config file is empty: {config_path}"
                raise ValueError(msg)
            return AppConfig(**data)
    except yaml.YAMLError as e:
        msg = f"Invalid YAML file: {e}"
        raise ValueError(msg) from e
