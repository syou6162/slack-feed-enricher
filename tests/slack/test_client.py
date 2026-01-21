"""SlackClientのテスト"""

from slack_feed_enricher.slack.client import SlackMessage


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
