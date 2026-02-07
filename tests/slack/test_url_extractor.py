"""URL抽出機能のテスト"""

from slack_feed_enricher.slack.client import SlackMessage
from slack_feed_enricher.slack.url_extractor import ExtractedUrls, extract_urls


class TestExtractUrls:
    """extract_urls関数のテスト"""

    def test_empty_text(self) -> None:
        """空テキスト → main_url=None, supplementary_urls=[]"""
        message = SlackMessage(ts="123", text="", reply_count=0)
        result = extract_urls(message)
        assert result == ExtractedUrls(main_url=None, supplementary_urls=[])

    def test_no_urls(self) -> None:
        """URLなしテキスト → main_url=None, supplementary_urls=[]"""
        message = SlackMessage(ts="123", text="これはテストメッセージです。URLは含まれていません。", reply_count=0)
        result = extract_urls(message)
        assert result == ExtractedUrls(main_url=None, supplementary_urls=[])

    def test_single_plain_url(self) -> None:
        """プレーンURL1つ → main_url="...", supplementary_urls=[]"""
        message = SlackMessage(ts="123", text="https://example.com を参照", reply_count=0)
        result = extract_urls(message)
        assert result == ExtractedUrls(main_url="https://example.com", supplementary_urls=[])

    def test_single_slack_format_url_with_label(self) -> None:
        """Slack形式URL1つ（表示テキスト付き） → main_url="...", supplementary_urls=[]"""
        message = SlackMessage(ts="123", text="記事: <https://example.com|Example>", reply_count=0)
        result = extract_urls(message)
        assert result == ExtractedUrls(main_url="https://example.com", supplementary_urls=[])

    def test_single_slack_format_url_without_label(self) -> None:
        """Slack形式URL1つ（表示テキストなし） → main_url="...", supplementary_urls=[]"""
        message = SlackMessage(ts="123", text="記事: <https://example.com>", reply_count=0)
        result = extract_urls(message)
        assert result == ExtractedUrls(main_url="https://example.com", supplementary_urls=[])

    def test_multiple_plain_urls(self) -> None:
        """プレーンURL2つ以上 → main_url="1つ目", supplementary_urls=["2つ目", ...]"""
        message = SlackMessage(
            ts="123",
            text="https://example1.com と https://example2.com と https://example3.com を参照",
            reply_count=0,
        )
        result = extract_urls(message)
        assert result == ExtractedUrls(
            main_url="https://example1.com",
            supplementary_urls=["https://example2.com", "https://example3.com"],
        )

    def test_mixed_slack_and_plain_urls(self) -> None:
        """Slack形式とプレーンURLの混在パターン（出現順で統合）"""
        message = SlackMessage(
            ts="123",
            text="<https://example1.com|記事> について https://example2.com も参照",
            reply_count=0,
        )
        result = extract_urls(message)
        assert result == ExtractedUrls(
            main_url="https://example1.com",
            supplementary_urls=["https://example2.com"],
        )

    def test_mixed_plain_then_slack_urls(self) -> None:
        """プレーンURLが先、Slack形式が後の混在パターン（出現順で統合）"""
        message = SlackMessage(
            ts="123",
            text="https://example1.com について <https://example2.com|補足>",
            reply_count=0,
        )
        result = extract_urls(message)
        assert result == ExtractedUrls(
            main_url="https://example1.com",
            supplementary_urls=["https://example2.com"],
        )

    def test_duplicate_url_deduplication(self) -> None:
        """同一URLの重複排除（Slack形式とプレーンURLで同じURLが出現する場合）"""
        message = SlackMessage(
            ts="123",
            text="<https://example.com|記事> について https://example.com も参照 https://other.com",
            reply_count=0,
        )
        result = extract_urls(message)
        assert result == ExtractedUrls(
            main_url="https://example.com",
            supplementary_urls=["https://other.com"],
        )

    def test_multiple_slack_format_urls(self) -> None:
        """Slack形式URL複数（表示テキストあり・なし混在）"""
        message = SlackMessage(
            ts="123",
            text="<https://example1.com|記事> と <https://example2.com> を参照",
            reply_count=0,
        )
        result = extract_urls(message)
        assert result == ExtractedUrls(
            main_url="https://example1.com",
            supplementary_urls=["https://example2.com"],
        )
