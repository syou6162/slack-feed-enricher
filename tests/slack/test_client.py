"""SlackClientのテスト"""

from unittest.mock import AsyncMock

import pytest

from slack_feed_enricher.slack.blocks import SlackBlock, SlackSectionBlock, SlackTextObject
from slack_feed_enricher.slack.client import SlackClient, SlackMessage
from slack_feed_enricher.slack.exceptions import SlackAPIError


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


@pytest.mark.asyncio
async def test_fetch_unreplied_messages_filters_replied() -> None:
    """返信済みメッセージをスキップして未返信メッセージのみ返すこと"""
    mock_client = AsyncMock()
    mock_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1", "text": "msg1", "reply_count": 0},
            {"ts": "2", "text": "msg2", "reply_count": 5},  # 返信あり
            {"ts": "3", "text": "msg3", "reply_count": 0},
        ],
    }

    client = SlackClient(mock_client)
    messages = await client.fetch_unreplied_messages("C0123456789")

    assert len(messages) == 2
    assert messages[0].ts == "1"
    assert messages[1].ts == "3"


@pytest.mark.asyncio
async def test_fetch_unreplied_messages_all_replied() -> None:
    """全てのメッセージが返信済みの場合は空リストを返すこと"""
    mock_client = AsyncMock()
    mock_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"ts": "1", "text": "msg1", "reply_count": 2},
            {"ts": "2", "text": "msg2", "reply_count": 1},
        ],
    }

    client = SlackClient(mock_client)
    messages = await client.fetch_unreplied_messages("C0123456789")

    assert len(messages) == 0


@pytest.mark.asyncio
async def test_post_thread_reply_success() -> None:
    """スレッド返信が正常に投稿できること"""
    mock_client = AsyncMock()
    mock_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567892.123456",
        "channel": "C0123456789",
        "message": {
            "ts": "1234567892.123456",
            "text": "テスト返信メッセージ",
        },
    }

    client = SlackClient(mock_client)
    result_ts = await client.post_thread_reply(
        channel_id="C0123456789",
        thread_ts="1234567890.123456",
        text="テスト返信メッセージ",
    )

    assert result_ts == "1234567892.123456"
    mock_client.chat_postMessage.assert_called_once_with(
        channel="C0123456789",
        thread_ts="1234567890.123456",
        text="テスト返信メッセージ",
    )


@pytest.mark.asyncio
async def test_post_thread_reply_api_error() -> None:
    """API呼び出しが失敗した場合に適切にエラーハンドリングすること"""
    mock_client = AsyncMock()
    mock_client.chat_postMessage.return_value = {
        "ok": False,
        "error": "channel_not_found",
    }

    client = SlackClient(mock_client)

    with pytest.raises(SlackAPIError) as exc_info:
        await client.post_thread_reply(
            channel_id="C_INVALID",
            thread_ts="1234567890.123456",
            text="テストメッセージ",
        )

    assert exc_info.value.error_code == "channel_not_found"


@pytest.mark.asyncio
async def test_post_thread_reply_with_markdown() -> None:
    """Markdown形式のテキストがそのまま送信されること"""
    mock_client = AsyncMock()
    markdown_text = """## 記事の要約

- ポイント1
- ポイント2

**重要**: これは重要なテキストです。"""

    mock_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567892.123456",
    }

    client = SlackClient(mock_client)
    await client.post_thread_reply(
        channel_id="C0123456789",
        thread_ts="1234567890.123456",
        text=markdown_text,
    )

    call_args = mock_client.chat_postMessage.call_args
    assert call_args.kwargs["text"] == markdown_text


@pytest.mark.asyncio
async def test_post_thread_reply_with_blocks() -> None:
    """blocksパラメータが指定された場合、chat_postMessageにblocksが渡されること"""
    mock_client = AsyncMock()
    mock_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567892.123456",
    }

    blocks: list[SlackBlock] = [
        SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text="*テスト*")),
    ]

    client = SlackClient(mock_client)
    await client.post_thread_reply(
        channel_id="C0123456789",
        thread_ts="1234567890.123456",
        text="フォールバックテキスト",
        blocks=blocks,
    )

    call_args = mock_client.chat_postMessage.call_args
    assert call_args.kwargs["blocks"] == [{"type": "section", "text": {"type": "mrkdwn", "text": "*テスト*"}}]
    assert call_args.kwargs["text"] == "フォールバックテキスト"


@pytest.mark.asyncio
async def test_post_thread_reply_without_blocks() -> None:
    """blocksパラメータが省略された場合、chat_postMessageにblocksが渡されないこと"""
    mock_client = AsyncMock()
    mock_client.chat_postMessage.return_value = {
        "ok": True,
        "ts": "1234567892.123456",
    }

    client = SlackClient(mock_client)
    await client.post_thread_reply(
        channel_id="C0123456789",
        thread_ts="1234567890.123456",
        text="テキストのみ",
    )

    call_args = mock_client.chat_postMessage.call_args
    assert "blocks" not in call_args.kwargs
