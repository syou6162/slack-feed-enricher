"""環境変数設定"""

import os

from pydantic import BaseModel, Field, ValidationError


class EnvConfig(BaseModel):
    """環境変数設定"""

    slack_bot_token: str = Field(..., description="Slack Bot User OAuth Token (xoxb-)")
    rss_feed_channel_id: str = Field(..., description="RSS feed投稿先のSlackチャンネルID")

    model_config = {"extra": "forbid"}


def load_env_config() -> EnvConfig:
    """環境変数からEnvConfigを読み込む

    Returns:
        EnvConfig: 環境変数設定

    Raises:
        ValueError: 必須環境変数が欠けている場合
    """
    try:
        return EnvConfig(
            slack_bot_token=os.environ["SLACK_BOT_TOKEN"],
            rss_feed_channel_id=os.environ["RSS_FEED_CHANNEL_ID"],
        )
    except KeyError as e:
        msg = f"Required environment variable is missing: {e}"
        raise ValueError(msg) from e
    except ValidationError as e:
        msg = f"Invalid environment variable: {e}"
        raise ValueError(msg) from e
