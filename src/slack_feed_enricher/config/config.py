"""統合Config クラス"""

from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from slack_feed_enricher.config.app import load_app_config
from slack_feed_enricher.config.env import load_env_config


class Config(BaseModel):
    """統合設定クラス（環境変数 + アプリケーション設定）"""

    # 環境変数由来
    slack_bot_token: str = Field(..., description="Slack Bot User OAuth Token (xoxb-)")
    rss_feed_channel_id: str = Field(..., description="RSS feed投稿先のSlackチャンネルID")

    # config.yaml由来
    polling_interval: int = Field(default=600, description="ポーリング間隔（秒）")
    message_limit: int = Field(default=10, description="取得メッセージ数")

    model_config = {"extra": "forbid"}


def load_config(config_path: Path) -> Config:
    """環境変数とYAMLファイルから統合設定を読み込む

    Args:
        config_path: YAMLファイルのパス

    Returns:
        Config: 統合設定

    Raises:
        ValueError: 必須の環境変数が欠けている場合
        FileNotFoundError: YAMLファイルが存在しない場合
    """
    # .envファイルを読み込み
    load_dotenv()

    env_config = load_env_config()
    app_config = load_app_config(config_path)

    return Config(
        slack_bot_token=env_config.slack_bot_token,
        rss_feed_channel_id=env_config.rss_feed_channel_id,
        polling_interval=app_config.polling_interval,
        message_limit=app_config.message_limit,
    )
