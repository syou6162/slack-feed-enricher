"""Slack API操作を担当するクライアントクラス"""

from dataclasses import dataclass

from slack_sdk.web.async_client import AsyncWebClient

from slack_feed_enricher.slack.exceptions import SlackAPIError


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
        response = await self._client.conversations_history(
            channel=channel_id,
            limit=limit,
        )

        if not response.get("ok"):
            error = response.get("error", "unknown_error")
            raise ValueError(error)

        messages = []
        for msg in response["messages"]:
            messages.append(
                SlackMessage(
                    ts=msg["ts"],
                    text=msg.get("text", ""),
                    reply_count=msg.get("reply_count", 0),
                )
            )

        return messages

    async def has_thread_replies(self, channel_id: str, message_ts: str) -> bool:
        """メッセージにスレッド返信があるかを確認"""
        response = await self._client.conversations_replies(
            channel=channel_id,
            ts=message_ts,
            limit=2,
        )

        if not response.get("ok"):
            error = response.get("error", "unknown_error")
            raise ValueError(error)

        # messages配列の最初は親メッセージ
        # 2件以上あれば返信がある
        return len(response["messages"]) > 1

    async def fetch_unreplied_messages(self, channel_id: str, limit: int = 100) -> list[SlackMessage]:
        """返信のないメッセージのみをフィルタリングして取得"""
        all_messages = await self.fetch_channel_history(channel_id, limit)

        # reply_countが0のメッセージのみをフィルタリング
        return [msg for msg in all_messages if msg.reply_count == 0]

    async def post_thread_reply(self, channel_id: str, thread_ts: str, text: str) -> str:
        """スレッドに返信を投稿する

        Args:
            channel_id: 投稿先のチャンネルID
            thread_ts: 返信先の親メッセージのタイムスタンプ
            text: 投稿するメッセージ本文（Markdown形式）

        Returns:
            str: 投稿されたメッセージのタイムスタンプ（ts）

        Raises:
            SlackAPIError: Slack API呼び出しでエラーが発生した場合
        """
        response = await self._client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=text,
        )

        if not response.get("ok"):
            error_code = response.get("error", "unknown_error")
            raise SlackAPIError(f"Failed to post thread reply: {error_code}", error_code)

        return response["ts"]
