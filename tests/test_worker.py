"""workerモジュールのテスト"""

from unittest.mock import AsyncMock

import pytest

from slack_feed_enricher.worker import send_enriched_messages


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
