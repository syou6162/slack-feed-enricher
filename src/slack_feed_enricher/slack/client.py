"""Slack API操作を担当するクライアントクラス"""

from dataclasses import dataclass

from slack_sdk.web.async_client import AsyncWebClient


@dataclass
class SlackMessage:
    """Slackメッセージを表すデータクラス"""

    ts: str  # メッセージのタイムスタンプ（スレッド返信時にthread_tsとして使用）
    text: str  # メッセージ本文（URL抽出用）
    reply_count: int  # 返信数（0なら未返信）


class SlackClient:
    """Slack API操作を担当するクライアントクラス"""

    def __init__(self, client: AsyncWebClient) -> None:
        """依存注入でAsyncWebClientを受け取る"""
        self._client = client

    async def fetch_channel_history(self, channel_id: str, limit: int = 100) -> list[SlackMessage]:
        """チャンネルの履歴をN件取得"""
        raise NotImplementedError

    async def has_thread_replies(self, channel_id: str, message_ts: str) -> bool:
        """メッセージにスレッド返信があるかを確認"""
        raise NotImplementedError

    async def fetch_unreplied_messages(self, channel_id: str, limit: int = 100) -> list[SlackMessage]:
        """返信のないメッセージのみをフィルタリングして取得"""
        raise NotImplementedError
