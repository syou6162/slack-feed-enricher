"""ポーリングワーカー"""

import asyncio
import logging
import time
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
    texts: list[str],
) -> list[str]:
    """
    要約テキストをSlackスレッドに順次投稿する。

    投稿順序: メタ情報 → 簡潔な要約 → 詳細

    Args:
        slack_client: Slackクライアント
        channel_id: チャンネルID
        thread_ts: スレッドのタイムスタンプ
        texts: 投稿するテキストのリスト

    Returns:
        list[str]: 投稿されたメッセージのtsリスト

    Raises:
        SlackAPIError: Slack API呼び出しに失敗した場合（途中で発生した場合は即座にraise）
    """
    reply_ts_list: list[str] = []
    for i, text in enumerate(texts):
        if i > 0:
            await asyncio.sleep(1.0)
        reply_ts = await slack_client.post_thread_reply(
            channel_id=channel_id,
            thread_ts=thread_ts,
            text=text,
        )
        reply_ts_list.append(reply_ts)
    return reply_ts_list


async def enrich_and_reply_pending_messages(
    slack_client: SlackClient,
    query_func: QueryFunc,
    channel_id: str,
    message_limit: int,
    timeout: int | None = None,  # タイムアウト秒数（Noneなら無制限）
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
    start_time = time.time()

    for i, message in enumerate(messages):
        # タイムアウトチェック
        if timeout is not None:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                remaining_count = len(messages) - i
                logger.warning(
                    f"タイムアウト: {elapsed:.1f}秒経過、残り{remaining_count}件のメッセージは未処理"
                )
                return EnrichAndReplyResult(
                    processed_count=i,
                    success_count=success_count,
                    error_count=error_count,
                    skipped_count=skipped_count,
                    timed_out=True,
                    remaining_count=remaining_count,
                )

        try:
            extracted = extract_urls(message)
            if extracted.main_url is None:
                skipped_count += 1
                continue

            blocks = await fetch_and_summarize(query_func, extracted.main_url, extracted.supplementary_urls)
            await send_enriched_messages(
                slack_client=slack_client,
                channel_id=channel_id,
                thread_ts=message.ts,
                texts=blocks,
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
                timeout=polling_interval,
            )
            await asyncio.sleep(polling_interval)
    except asyncio.CancelledError:
        logger.info("ポーリングループがキャンセルされました")
        raise
    finally:
        logger.info("ポーリングループ終了")
