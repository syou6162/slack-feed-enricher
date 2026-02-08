"""workerモジュールのテスト"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from unittest.mock import AsyncMock, patch

import pytest
from claude_agent_sdk import ResultMessage

from slack_feed_enricher.claude.summarizer import EnrichResult, Meta, Summary, build_detail_blocks, build_meta_blocks, build_summary_blocks
from slack_feed_enricher.hatebu.models import HatebuBookmark, HatebuEntry
from slack_feed_enricher.slack import SlackMessage
from slack_feed_enricher.slack.exceptions import SlackAPIError
from slack_feed_enricher.slack.url_extractor import ExtractedUrls
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

# テスト用のEnrichResultヘルパー
_SAMPLE_META = Meta(
    title="テスト記事",
    url="https://example.com",
    author="test_author",
    category_large="テスト",
    category_medium="サブカテゴリ",
    published_at="2025-01-15T10:30:00Z",
)
_SAMPLE_SUMMARY = Summary(points=["ポイント1"])

SAMPLE_ENRICH_RESULT = EnrichResult(
    meta_blocks=build_meta_blocks(_SAMPLE_META),
    meta_text="*テスト記事*\nURL: https://example.com\n著者: test_author\nカテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z",
    summary_blocks=build_summary_blocks(_SAMPLE_SUMMARY),
    summary_text="- ポイント1",
    detail_blocks=build_detail_blocks("# 詳細\n記事の詳細内容"),
    detail_text="*詳細*\n記事の詳細内容",
)


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
async def test_send_enriched_messages_posts_three_messages_with_blocks() -> None:
    """EnrichResultから3通のメッセージが投稿され、1,2通目はblocks付き、3通目はtextのみであること"""

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
        result=SAMPLE_ENRICH_RESULT,
    )

    assert result == ["ts_meta", "ts_summary", "ts_detail"]
    assert mock_slack_client.post_thread_reply.call_count == 3

    calls = mock_slack_client.post_thread_reply.call_args_list

    # 1通目: meta（blocks + text）
    assert calls[0].kwargs["text"] == SAMPLE_ENRICH_RESULT.meta_text
    assert calls[0].kwargs["blocks"] == SAMPLE_ENRICH_RESULT.meta_blocks

    # 2通目: summary（blocks + text）
    assert calls[1].kwargs["text"] == SAMPLE_ENRICH_RESULT.summary_text
    assert calls[1].kwargs["blocks"] == SAMPLE_ENRICH_RESULT.summary_blocks

    # 3通目: detail（blocks + text）
    assert calls[2].kwargs["text"] == SAMPLE_ENRICH_RESULT.detail_text
    assert calls[2].kwargs["blocks"] == SAMPLE_ENRICH_RESULT.detail_blocks


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
    # 各メッセージは3通投稿なので、side_effectも3倍必要
    # 1件目: 3通成功, 2件目: 1通目でエラー, 3件目: 3通成功
    mock_slack_client.post_thread_reply.side_effect = [
        "reply_ts_1a",  # msg1: meta
        "reply_ts_1b",  # msg1: summary
        "reply_ts_1c",  # msg1: detail
        SlackAPIError("エラー", "rate_limited"),  # msg2: meta（エラー）
        "reply_ts_3a",  # msg3: meta
        "reply_ts_3b",  # msg3: summary
        "reply_ts_3c",  # msg3: detail
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


@pytest.mark.asyncio
async def test_enrich_and_reply_with_hatebu_client() -> None:
    """hatebu_client付きでfetch_entryが呼ばれ、結果がfetch_and_summarizeに渡されること"""
    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example.com/article>", reply_count=0),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    mock_query_func = create_mock_query_func()

    mock_hatebu_client = AsyncMock()
    mock_hatebu_client.fetch_entry.return_value = HatebuEntry(
        count=3,
        bookmarks=[
            HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30"),
        ],
    )

    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=mock_query_func,
        channel_id="C0123456789",
        message_limit=100,
        hatebu_client=mock_hatebu_client,
    )

    assert result.success_count == 1
    assert result.error_count == 0
    # fetch_entryがURLで呼ばれたこと
    mock_hatebu_client.fetch_entry.assert_called_once_with("https://example.com/article")


@pytest.mark.asyncio
async def test_enrich_and_reply_hatebu_client_none_skips_fetch() -> None:
    """hatebu_client=Noneの場合、fetch_entryは呼ばれない（従来通り動作）"""
    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example.com/article>", reply_count=0),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    mock_query_func = create_mock_query_func()

    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=mock_query_func,
        channel_id="C0123456789",
        message_limit=100,
        hatebu_client=None,
    )

    assert result.success_count == 1
    assert result.error_count == 0


@pytest.mark.asyncio
async def test_enrich_and_reply_hatebu_client_error_continues() -> None:
    """hatebu_client.fetch_entryがExceptionを投げても処理が続行されること（フェイルオープン）"""
    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example.com/article>", reply_count=0),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    mock_query_func = create_mock_query_func()

    mock_hatebu_client = AsyncMock()
    mock_hatebu_client.fetch_entry.side_effect = Exception("Hatena API error")

    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=mock_query_func,
        channel_id="C0123456789",
        message_limit=100,
        hatebu_client=mock_hatebu_client,
    )

    # はてブ取得が失敗してもhatebu_entry=Noneで要約処理は続行される
    assert result.success_count == 1
    assert result.error_count == 0


@pytest.mark.asyncio
async def test_run_passes_hatebu_client() -> None:
    """run()がhatebu_clientをenrich_and_reply_pending_messagesに渡すこと"""
    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = []

    mock_query_func = create_mock_query_func()
    mock_hatebu_client = AsyncMock()

    task = asyncio.create_task(
        run(
            slack_client=mock_slack_client,
            query_func=mock_query_func,
            channel_id="C0123456789",
            message_limit=100,
            polling_interval=1,
            hatebu_client=mock_hatebu_client,
        )
    )

    await asyncio.sleep(0.1)
    task.cancel()

    with suppress(asyncio.CancelledError):
        await task

    mock_slack_client.fetch_unreplied_messages.assert_called()


@pytest.mark.asyncio
@patch("slack_feed_enricher.worker.resolve_urls", new_callable=AsyncMock)
async def test_enrich_and_reply_calls_resolve_urls(mock_resolve_urls: AsyncMock) -> None:
    """Google News URLを含むメッセージ処理時にresolve_urlsが呼ばれること"""
    mock_resolve_urls.return_value = ExtractedUrls(
        main_url="https://example.com/resolved-article",
        supplementary_urls=[],
    )

    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(
            ts="1",
            text="<https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5>",
            reply_count=0,
        ),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    mock_query_func = create_mock_query_func()

    result = await enrich_and_reply_pending_messages(
        slack_client=mock_slack_client,
        query_func=mock_query_func,
        channel_id="C0123456789",
        message_limit=100,
    )

    assert result.success_count == 1
    assert result.error_count == 0

    # resolve_urlsが呼ばれたことを確認
    mock_resolve_urls.assert_called_once()
    call_arg = mock_resolve_urls.call_args[0][0]
    assert call_arg.main_url == "https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"
