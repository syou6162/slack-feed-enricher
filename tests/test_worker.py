"""workerモジュールのテスト"""

from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ResultMessage

from slack_feed_enricher.slack import SlackMessage
from slack_feed_enricher.worker import enrich_and_reply_pending_messages, send_enriched_messages

QueryFunc = Callable[..., AsyncIterator[Any]]


@pytest.mark.asyncio
async def test_send_enriched_messages_posts_to_slack() -> None:
    """要約テキストがSlackスレッドに投稿されること"""

    mock_slack_client = AsyncMock()
    mock_slack_client.post_thread_reply.return_value = "1234567890.123456"

    result = await send_enriched_messages(
        slack_client=mock_slack_client,
        channel_id="C0123456789",
        thread_ts="1234567890.000000",
        text="# テスト要約\n\nこれはテストです。",
    )

    assert result == ["1234567890.123456"]
    mock_slack_client.post_thread_reply.assert_called_once_with(
        channel_id="C0123456789",
        thread_ts="1234567890.000000",
        text="# テスト要約\n\nこれはテストです。",
    )


@pytest.mark.asyncio
async def test_enrich_and_reply_pending_messages_processes_all() -> None:
    """未返信メッセージ全件が処理されること"""

    def create_mock_query_func(markdown: str) -> QueryFunc:
        async def mock_query(*args: object, **kwargs: object) -> AsyncIterator[ResultMessage]:
            yield ResultMessage(
                is_error=False,
                result="success",
                structured_output={"markdown": markdown},
                subtype="normal",
                duration_ms=1000,
                duration_api_ms=800,
                num_turns=1,
                session_id="test-session",
            )

        return mock_query

    mock_slack_client = AsyncMock()
    mock_slack_client.fetch_unreplied_messages.return_value = [
        SlackMessage(ts="1", text="<https://example1.com>", reply_count=0),
        SlackMessage(ts="2", text="<https://example2.com>", reply_count=0),
        SlackMessage(ts="3", text="URLなし", reply_count=0),
    ]
    mock_slack_client.post_thread_reply.return_value = "reply_ts"

    mock_query_func = create_mock_query_func("# 要約")

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
