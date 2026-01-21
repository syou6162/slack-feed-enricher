"""URL抽出機能のテスト"""

from slack_feed_enricher.slack.client import SlackMessage
from slack_feed_enricher.slack.url_extractor import extract_urls


def test_extract_urls_empty_text() -> None:
    """空のテキストから空リストが返ること"""
    message = SlackMessage(ts="123", text="", reply_count=0)
    result = extract_urls(message)
    assert result == []


def test_extract_urls_no_urls() -> None:
    """URLが含まれていないテキストから空リストが返ること"""
    message = SlackMessage(ts="123", text="これはテストメッセージです。URLは含まれていません。", reply_count=0)
    result = extract_urls(message)
    assert result == []


def test_extract_urls_slack_format_with_label() -> None:
    """Slack形式（表示テキスト付き）のURLが抽出できること"""
    message = SlackMessage(ts="123", text="記事: <https://example.com|Example>", reply_count=0)
    result = extract_urls(message)
    assert result == ["https://example.com"]


def test_extract_urls_plain_url() -> None:
    """プレーンURLが抽出できること"""
    message = SlackMessage(ts="123", text="https://example.com を参照", reply_count=0)
    result = extract_urls(message)
    assert result == ["https://example.com"]


def test_extract_urls_removes_duplicates() -> None:
    """重複URLが除去されること"""
    message = SlackMessage(ts="123", text="https://example.com と https://example.com を参照", reply_count=0)
    result = extract_urls(message)
    assert result == ["https://example.com"]
    assert len(result) == 1
