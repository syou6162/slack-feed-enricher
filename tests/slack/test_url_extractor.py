"""URL抽出機能のテスト"""

from slack_feed_enricher.slack.client import SlackMessage
from slack_feed_enricher.slack.url_extractor import extract_url


def test_extract_url_empty_text() -> None:
    """空のテキストからNoneが返ること"""
    message = SlackMessage(ts="123", text="", reply_count=0)
    result = extract_url(message)
    assert result is None


def test_extract_url_no_urls() -> None:
    """URLが含まれていないテキストからNoneが返ること"""
    message = SlackMessage(ts="123", text="これはテストメッセージです。URLは含まれていません。", reply_count=0)
    result = extract_url(message)
    assert result is None


def test_extract_url_slack_format_with_label() -> None:
    """Slack形式（表示テキスト付き）のURLが抽出できること"""
    message = SlackMessage(ts="123", text="記事: <https://example.com|Example>", reply_count=0)
    result = extract_url(message)
    assert result == "https://example.com"


def test_extract_url_plain_url() -> None:
    """プレーンURLが抽出できること"""
    message = SlackMessage(ts="123", text="https://example.com を参照", reply_count=0)
    result = extract_url(message)
    assert result == "https://example.com"


def test_extract_url_returns_first_url() -> None:
    """複数URLがある場合、先頭のURLのみが返ること"""
    message = SlackMessage(ts="123", text="https://example1.com と https://example2.com を参照", reply_count=0)
    result = extract_url(message)
    assert result == "https://example1.com"
