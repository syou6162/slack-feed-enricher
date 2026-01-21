"""ポーリングワーカー"""

from slack_feed_enricher.slack import SlackClient


async def send_enriched_messages(
    slack_client: SlackClient,
    channel_id: str,
    thread_ts: str,
    text: str,
) -> list[str]:
    """
    要約テキストをSlackスレッドに投稿する。

    Returns:
        list[str]: 投稿されたメッセージのtsリスト（現時点では要素1つ）

    Raises:
        SlackAPIError: Slack API呼び出しに失敗した場合

    Note:
        メッセージ分割機能は後段タスクで実装予定。
        現時点ではpost_thread_replyを1回呼び、要素1つのリストを返す。
    """
    reply_ts = await slack_client.post_thread_reply(
        channel_id=channel_id,
        thread_ts=thread_ts,
        text=text,
    )
    return [reply_ts]
