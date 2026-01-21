"""ポーリングワーカー"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from slack_feed_enricher.claude import fetch_and_summarize
from slack_feed_enricher.slack import SlackClient, extract_urls

logger = logging.getLogger(__name__)

QueryFunc = Callable[..., AsyncIterator[Any]]


@dataclass
class EnrichAndReplyResult:
    """enrich_and_reply_pending_messagesの結果"""

    processed_count: int
    success_count: int
    error_count: int
    skipped_count: int  # URLがないメッセージ
    timed_out: bool = False
    remaining_count: int = 0  # タイムアウト時の未処理メッセージ数


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


async def enrich_and_reply_pending_messages(
    slack_client: SlackClient,
    query_func: QueryFunc,
    channel_id: str,
    message_limit: int,
    timeout: int | None = None,  # タイムアウト秒数（Noneなら無制限）  # noqa: ARG001
) -> EnrichAndReplyResult:
    """
    未返信メッセージをエンリッチして返信する。

    Args:
        slack_client: Slackクライアント
        query_func: Claude Agent SDKのquery関数
        channel_id: チャンネルID
        message_limit: 取得するメッセージ数
        timeout: タイムアウト秒数（Noneなら無制限）

    Returns:
        EnrichAndReplyResult: 処理結果
    """
    messages = await slack_client.fetch_unreplied_messages(channel_id, limit=message_limit)

    success_count = 0
    error_count = 0
    skipped_count = 0

    for message in messages:
        try:
            urls = extract_urls(message)
            if not urls:
                skipped_count += 1
                continue

            summary = await fetch_and_summarize(query_func, urls)
            await send_enriched_messages(
                slack_client=slack_client,
                channel_id=channel_id,
                thread_ts=message.ts,
                text=summary,
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Error processing message {message.ts}: {e!r}")
            error_count += 1

    return EnrichAndReplyResult(
        processed_count=len(messages),
        success_count=success_count,
        error_count=error_count,
        skipped_count=skipped_count,
    )


async def run(
    slack_client: SlackClient,
    query_func: QueryFunc,
    channel_id: str,
    message_limit: int,
    polling_interval: int,
) -> None:
    """
    ポーリングループを実行する。

    Args:
        slack_client: Slackクライアント
        query_func: Claude Agent SDKのquery関数
        channel_id: チャンネルID
        message_limit: 取得するメッセージ数
        polling_interval: ポーリング間隔（秒）
    """
    logger.info("ポーリングループ開始: polling_interval=%d秒", polling_interval)

    try:
        while True:
            await enrich_and_reply_pending_messages(
                slack_client=slack_client,
                query_func=query_func,
                channel_id=channel_id,
                message_limit=message_limit,
            )
            await asyncio.sleep(polling_interval)
    except asyncio.CancelledError:
        logger.info("ポーリングループがキャンセルされました")
        raise
    finally:
        logger.info("ポーリングループ終了")
