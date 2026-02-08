"""ポーリングワーカー"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from slack_feed_enricher.claude import fetch_and_summarize
from slack_feed_enricher.claude.summarizer import EnrichResult
from slack_feed_enricher.hatebu.client import HatebuClient
from slack_feed_enricher.slack import SlackClient, extract_urls, resolve_urls

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
    result: EnrichResult,
) -> list[str]:
    """
    EnrichResultをSlackスレッドに3通のメッセージとして投稿する。

    投稿順序:
    1. メタ情報（Block Kit + フォールバックtext）
    2. 簡潔な要約（Block Kit + フォールバックtext）
    3. 詳細（Block Kit + フォールバックtext）

    Args:
        slack_client: Slackクライアント
        channel_id: チャンネルID
        thread_ts: スレッドのタイムスタンプ
        result: EnrichResult（Block Kit形式のブロックとフォールバックテキスト）

    Returns:
        list[str]: 投稿されたメッセージのtsリスト

    Raises:
        SlackAPIError: Slack API呼び出しに失敗した場合（途中で発生した場合は即座にraise）
    """
    # 1通目: meta（blocks + text）
    ts_meta = await slack_client.post_thread_reply(
        channel_id=channel_id,
        thread_ts=thread_ts,
        text=result.meta_text,
        blocks=result.meta_blocks,
    )

    await asyncio.sleep(1.0)

    # 2通目: summary（blocks + text）
    ts_summary = await slack_client.post_thread_reply(
        channel_id=channel_id,
        thread_ts=thread_ts,
        text=result.summary_text,
        blocks=result.summary_blocks,
    )

    await asyncio.sleep(1.0)

    # 3通目: detail（blocks + text）
    ts_detail = await slack_client.post_thread_reply(
        channel_id=channel_id,
        thread_ts=thread_ts,
        text=result.detail_text,
        blocks=result.detail_blocks,
    )

    return [ts_meta, ts_summary, ts_detail]


async def enrich_and_reply_pending_messages(
    slack_client: SlackClient,
    query_func: QueryFunc,
    channel_id: str,
    message_limit: int,
    timeout: int | None = None,  # タイムアウト秒数（Noneなら無制限）
    hatebu_client: HatebuClient | None = None,
) -> EnrichAndReplyResult:
    """
    未返信メッセージをエンリッチして返信する。

    Args:
        slack_client: Slackクライアント
        query_func: Claude Agent SDKのquery関数
        channel_id: チャンネルID
        message_limit: 取得するメッセージ数
        timeout: タイムアウト秒数（Noneなら無制限）
        hatebu_client: はてなブックマーククライアント（Noneならはてブ連携なし）

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

            resolved = await resolve_urls(extracted)
            if resolved.main_url is None:
                skipped_count += 1
                continue

            # はてブエントリー取得（フェイルオープン）
            hatebu_entry = None
            if hatebu_client is not None:
                try:
                    hatebu_entry = await hatebu_client.fetch_entry(resolved.main_url)
                except Exception:
                    logger.warning(f"はてブ取得失敗 (URL: {resolved.main_url}), hatebu_entry=Noneで続行")

            enrich_result = await fetch_and_summarize(
                query_func, resolved.main_url, resolved.supplementary_urls, hatebu_entry=hatebu_entry
            )
            await send_enriched_messages(
                slack_client=slack_client,
                channel_id=channel_id,
                thread_ts=message.ts,
                result=enrich_result,
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
    hatebu_client: HatebuClient | None = None,
) -> None:
    """
    ポーリングループを実行する。

    Args:
        slack_client: Slackクライアント
        query_func: Claude Agent SDKのquery関数
        channel_id: チャンネルID
        message_limit: 取得するメッセージ数
        polling_interval: ポーリング間隔（秒）
        hatebu_client: はてなブックマーククライアント（Noneならはてブ連携なし）
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
                hatebu_client=hatebu_client,
            )
            await asyncio.sleep(polling_interval)
    except asyncio.CancelledError:
        logger.info("ポーリングループがキャンセルされました")
        raise
    finally:
        logger.info("ポーリングループ終了")
