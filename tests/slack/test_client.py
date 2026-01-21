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


@pytest.mark.asyncio
async def test_fetch_channel_history_success() -> None:
    """チャンネル履歴が正常に取得できること"""
    mock_client = AsyncMock()
    mock_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {
                "ts": "1234567890.123456",
                "text": "テストメッセージ1",
                "user": "U123",
                "reply_count": 0,
            },
            {
                "ts": "1234567891.123456",
                "text": "テストメッセージ2",
                "user": "U456",
                "thread_ts": "1234567890.123456",
                "reply_count": 3,
            },
        ],
    }

    client = SlackClient(mock_client)
    messages = await client.fetch_channel_history("C0123456789", limit=10)

    assert len(messages) == 2
    assert messages[0].ts == "1234567890.123456"
    assert messages[0].text == "テストメッセージ1"
    assert messages[0].reply_count == 0
    assert messages[1].ts == "1234567891.123456"
    assert messages[1].reply_count == 3

    mock_client.conversations_history.assert_called_once_with(
        channel="C0123456789",
        limit=10,
    )


@pytest.mark.asyncio
async def test_fetch_channel_history_api_error() -> None:
    """API呼び出しが失敗した場合に適切にエラーハンドリングすること"""
    mock_client = AsyncMock()
    mock_client.conversations_history.return_value = {
        "ok": False,
        "error": "channel_not_found",
    }

    client = SlackClient(mock_client)

    with pytest.raises(ValueError, match="channel_not_found"):
        await client.fetch_channel_history("C_INVALID")


@pytest.mark.asyncio
async def test_has_thread_replies_with_replies() -> None:
    """スレッド返信がある場合にTrueを返すこと"""
    mock_client = AsyncMock()
    mock_client.conversations_replies.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1234567890.123456", "text": "親メッセージ"},
            {"ts": "1234567891.123456", "text": "返信1"},
        ],
    }

    client = SlackClient(mock_client)
    result = await client.has_thread_replies("C0123456789", "1234567890.123456")

    assert result is True
    mock_client.conversations_replies.assert_called_once_with(
        channel="C0123456789",
        ts="1234567890.123456",
        limit=2,
    )


@pytest.mark.asyncio
async def test_has_thread_replies_without_replies() -> None:
    """スレッド返信がない場合にFalseを返すこと"""
    mock_client = AsyncMock()
    mock_client.conversations_replies.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1234567890.123456", "text": "親メッセージのみ"},
        ],
    }

    client = SlackClient(mock_client)
    result = await client.has_thread_replies("C0123456789", "1234567890.123456")

    assert result is False


@pytest.mark.asyncio
async def test_has_thread_replies_api_error() -> None:
    """API呼び出しが失敗した場合の処理"""
    mock_client = AsyncMock()
    mock_client.conversations_replies.return_value = {
        "ok": False,
        "error": "thread_not_found",
    }

    client = SlackClient(mock_client)

    with pytest.raises(ValueError, match="thread_not_found"):
        await client.has_thread_replies("C0123456789", "invalid_ts")
