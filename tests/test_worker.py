"""workerモジュールのテスト"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ResultMessage

from slack_feed_enricher.slack import SlackMessage
from slack_feed_enricher.slack.exceptions import SlackAPIError
from slack_feed_enricher.worker import QueryFunc, enrich_and_reply_pending_messages, run, send_enriched_messages

# テスト用の3ブロック構造化出力を生成するヘルパー
SAMPLE_STRUCTURED_OUTPUT = {
    "meta": {
        "title": "テスト記事",
        "url": "https://example.com",
        "author": "test_author",
        "category_large": "テスト",
        "category_medium": "サブカテゴリ",
        "published_at": "2025-01-15T10:30:00Z",
    },
    "summary": {"points": ["ポイント1"]},
    "detail": "# 詳細\n記事の詳細内容",
}


def create_mock_query_func() -> QueryFunc:
    """3ブロック構造のResultMessageを返すモックquery関数"""

    async def mock_query(*args: object, **kwargs: object) -> AsyncIterator[ResultMessage]:
        yield ResultMessage(
            is_error=False,
            result="success",
            structured_output=SAMPLE_STRUCTURED_OUTPUT,
            subtype="normal",
            duration_ms=1000,
            duration_api_ms=800,
            num_turns=1,
            session_id="test-session",
        )

    return mock_query


@pytest.mark.asyncio
async def test_send_enriched_messages_posts_multiple_blocks_to_slack() -> None:
    """複数ブロックがSlackスレッドに順次投稿されること"""

    mock_slack_client = AsyncMock()
    mock_slack_client.post_thread_reply.side_effect = [
        "ts_meta",
        "ts_summary",
        "ts_detail",
    ]

    result = await send_enriched_messages(
        slack_client=mock_slack_client,
        channel_id="C0123456789",
        thread_ts="1234567890.000000",
        texts=["メタ情報テキスト", "要約テキスト", "詳細テキスト"],
    )

    assert result == ["ts_meta", "ts_summary", "ts_detail"]
    assert mock_slack_client.post_thread_reply.call_count == 3
    # 投稿順序の検証
    calls = mock_slack_client.post_thread_reply.call_args_list
    assert calls[0].kwargs["text"] == "メタ情報テキスト"
    assert calls[1].kwargs["text"] == "要約テキスト"
    assert calls[2].kwargs["text"] == "詳細テキスト"


@pytest.mark.asyncio
async def test_send_enriched_messages_single_block() -> None:
    """1ブロックのみの場合も正しく動作すること"""

    mock_slack_client = AsyncMock()
    mock_slack_client.post_thread_reply.return_value = "ts_single"

    result = await send_enriched_messages(
        slack_client=mock_slack_client,
        channel_id="C0123456789",
        thread_ts="1234567890.000000",
        texts=["単一テキスト"],
    )

    assert result == ["ts_single"]
    mock_slack_client.post_thread_reply.assert_called_once()


@pytest.mark.asyncio
async def test_enrich_and_reply_pending_messages_processes_all() -> None:
    """未返信メッセージ全件が処理されること"""

    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example1.com>", reply_count=0),
        SlackMessage(ts="2", text="<https://example2.com>", reply_count=0),
        SlackMessage(ts="3", text="URLなし", reply_count=0),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    mock_query_func = create_mock_query_func()

    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=mock_query_func,
        channel_id="C0123456789",
        message_limit=100,
    )

    assert result.processed_count == 3
    assert result.success_count == 2
    assert result.error_count == 0
    assert result.skipped_count == 1
    assert result.timed_out is False
    assert result.remaining_count == 0


@pytest.mark.asyncio
async def test_enrich_and_reply_pending_messages_continues_on_error() -> None:
    """1件のエラーで全体が止まらないことをテスト"""

    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example1.com>", reply_count=0),
        SlackMessage(ts="2", text="<https://example2.com>", reply_count=0),
        SlackMessage(ts="3", text="<https://example3.com>", reply_count=0),
    ]
    # 各メッセージは3ブロック投稿なので、side_effectも3倍必要
    # 1件目: 3ブロック成功, 2件目: 1ブロック目でエラー, 3件目: 3ブロック成功
    mock_slack_client.post_thread_reply.side_effect = [
        "reply_ts_1a",
        "reply_ts_1b",
        "reply_ts_1c",
        SlackAPIError("エラー", "rate_limited"),
        "reply_ts_3a",
        "reply_ts_3b",
        "reply_ts_3c",
    ]

    mock_query_func = create_mock_query_func()

    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=mock_query_func,
        channel_id="C0123456789",
        message_limit=100,
    )

    assert result.processed_count == 3
    assert result.success_count == 2
    assert result.error_count == 1


@pytest.mark.asyncio
async def test_run_calls_enrich_and_reply_pending_messages() -> None:
    """ポーリングループがenrich_and_reply_pending_messagesを呼び出すことをテスト"""

    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = []

    mock_query_func = create_mock_query_func()

    # 1回の呼び出し後にCancelledErrorを投げてループを止める
    task = asyncio.create_task(
        run(
            slack_client=mock_slack_client,
            query_func=mock_query_func,
            channel_id="C0123456789",
            message_limit=100,
            polling_interval=1,
        )
    )

    # 少し待ってからキャンセル
    await asyncio.sleep(0.1)
    task.cancel()

    with suppress(asyncio.CancelledError):
        await task

    # enrich_and_reply_pending_messagesが少なくとも1回呼ばれたことを確認
    mock_slack_client.fetch_unreplied_messages.assert_called()


@pytest.mark.asyncio
async def test_enrich_and_reply_pending_messages_timeout() -> None:
    """処理がtimeout秒を超えた場合に中断して結果を返すことをテスト"""

    async def slow_mock_query(*args: object, **kwargs: object) -> AsyncIterator[ResultMessage]:
        # 各クエリに2秒かかる
        await asyncio.sleep(2)
        yield ResultMessage(
            is_error=False,
            result="success",
            structured_output=SAMPLE_STRUCTURED_OUTPUT,
            subtype="normal",
            duration_ms=2000,
            duration_api_ms=1800,
            num_turns=1,
            session_id="test-session",
        )

    mock_slack_client = AsyncMock()
    # 5件のメッセージがあるが、タイムアウトで全部処理できない
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example1.com>", reply_count=0),
        SlackMessage(ts="2", text="<https://example2.com>", reply_count=0),
        SlackMessage(ts="3", text="<https://example3.com>", reply_count=0),
        SlackMessage(ts="4", text="<https://example4.com>", reply_count=0),
        SlackMessage(ts="5", text="<https://example5.com>", reply_count=0),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    # 1秒でタイムアウト（1件目は処理できるが、2件目の前にタイムアウト）
    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=slow_mock_query,
        channel_id="C0123456789",
        message_limit=100,
        timeout=1,
    )

    # 1件目は開始時elapsed=0なので処理が始まり完了する（2秒）
    # 2件目の開始前チェックでelapsed=2秒>timeout=1秒なのでタイムアウト
    assert result.timed_out is True
    assert result.success_count == 1
    assert result.remaining_count == 4
    assert result.processed_count == 1
