"""SlackClientのテスト"""

from unittest.mock import AsyncMock

import pytest

from slack_feed_enricher.slack.client import SlackClient, SlackMessage


def test_slack_message_creation() -> None:
    """SlackMessageが正しく作成できること"""

    msg = SlackMessage(
        ts="1234567890.123456",
        text="テストメッセージ",
        reply_count=0,
    )
    assert msg.ts == "1234567890.123456"
    assert msg.text == "テストメッセージ"
    assert msg.reply_count == 0


@pytest.mark.asyncio
async def test_slack_client_initialization() -> None:
    """SlackClientが正しく初期化できること"""
    mock_client = AsyncMock()
    client = SlackClient(mock_client)
    assert client._client is mock_client
