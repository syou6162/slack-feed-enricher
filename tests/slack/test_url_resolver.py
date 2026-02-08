"""URL解決機能のテスト"""

import logging
import time
from unittest.mock import patch

from slack_feed_enricher.slack.url_extractor import ExtractedUrls
from slack_feed_enricher.slack.url_resolver import is_google_news_url, resolve_url, resolve_urls


class TestIsGoogleNewsUrl:
    """is_google_news_url関数のテスト"""

    def test_rss_articles_url(self) -> None:
        """/rss/articles/CBMi...形式 → True"""
        url = "https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"
        assert is_google_news_url(url) is True

    def test_regular_url(self) -> None:
        """通常URL → False"""
        url = "https://example.com/article/123"
        assert is_google_news_url(url) is False

    def test_empty_string(self) -> None:
        """空文字列 → False"""
        assert is_google_news_url("") is False

    def test_google_news_topics_url(self) -> None:
        """/topics/形式はデコード不可 → False"""
        url = "https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtcGhHZ0pLVUNnQVAB?oc=3"
        assert is_google_news_url(url) is False

    def test_google_news_topstories_url(self) -> None:
        """/topstories形式はデコード不可 → False"""
        url = "https://news.google.com/topstories?hl=ja&gl=JP"
        assert is_google_news_url(url) is False

    def test_google_news_home_url(self) -> None:
        """Google Newsトップページ → False"""
        url = "https://news.google.com/"
        assert is_google_news_url(url) is False

    def test_http_scheme(self) -> None:
        """httpスキームでも判定可能"""
        url = "http://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"
        assert is_google_news_url(url) is True


class TestResolveUrl:
    """resolve_url関数のテスト"""

    async def test_non_google_news_url_returns_as_is(self) -> None:
        """非Google News URL → そのまま返る"""
        url = "https://example.com/article/123"
        result = await resolve_url(url)
        assert result == url

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_google_news_url_decode_success(self, mock_decoder: object) -> None:
        """Google News URL + デコード成功 → 解決後URLを返す"""
        mock_decoder.return_value = {"status": True, "decoded_url": "https://world-tt.com/blog/news/archives/329736"}  # type: ignore[union-attr]
        url = "https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"
        result = await resolve_url(url)
        assert result == "https://world-tt.com/blog/news/archives/329736"
        mock_decoder.assert_called_once_with(url)  # type: ignore[union-attr]

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_google_news_url_decode_failure_status_false(self, mock_decoder: object) -> None:
        """デコード失敗（status=False） → 元URLをフォールバック"""
        mock_decoder.return_value = {"status": False, "decoded_url": ""}  # type: ignore[union-attr]
        url = "https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"
        result = await resolve_url(url)
        assert result == url

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_google_news_url_decode_exception(self, mock_decoder: object) -> None:
        """例外発生 → 元URLをフォールバック"""
        mock_decoder.side_effect = Exception("Network error")  # type: ignore[union-attr]
        url = "https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"
        result = await resolve_url(url)
        assert result == url

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_google_news_url_timeout(self, mock_decoder: object, caplog: object) -> None:
        """タイムアウト発生 → 元URLをフォールバック + WARNINGログ"""

        def slow_decoder(url: str) -> dict[str, object]:
            time.sleep(30)
            return {"status": True, "decoded_url": "https://example.com"}

        mock_decoder.side_effect = slow_decoder  # type: ignore[union-attr]
        url = "https://news.google.com/rss/articles/CBMiWkFV_yqLPPG26S54Vr3FAAJZqPNByc?oc=5"

        with caplog.at_level(logging.WARNING, logger="slack_feed_enricher.slack.url_resolver"):  # type: ignore[union-attr]
            result = await resolve_url(url)

        assert result == url
        assert any("タイムアウト" in record.message for record in caplog.records)  # type: ignore[union-attr]


class TestResolveUrls:
    """resolve_urls関数のテスト"""

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_main_and_supplementary_urls_resolved(self, mock_decoder: object) -> None:
        """main_urlとsupplementary_urlsが両方解決される"""

        def decoder_side_effect(url: str) -> dict[str, object]:
            mapping = {
                "https://news.google.com/rss/articles/AAA": {"status": True, "decoded_url": "https://example.com/article1"},
                "https://news.google.com/rss/articles/BBB": {"status": True, "decoded_url": "https://example.com/article2"},
            }
            return mapping[url]

        mock_decoder.side_effect = decoder_side_effect  # type: ignore[union-attr]

        extracted = ExtractedUrls(
            main_url="https://news.google.com/rss/articles/AAA",
            supplementary_urls=["https://news.google.com/rss/articles/BBB"],
        )
        result = await resolve_urls(extracted)
        assert result.main_url == "https://example.com/article1"
        assert result.supplementary_urls == ["https://example.com/article2"]

    async def test_main_url_none_returns_as_is(self) -> None:
        """main_urlがNone → そのまま返る"""
        extracted = ExtractedUrls(main_url=None, supplementary_urls=[])
        result = await resolve_urls(extracted)
        assert result.main_url is None
        assert result.supplementary_urls == []

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_duplicate_main_and_supplementary_removed(self, mock_decoder: object) -> None:
        """解決後にmain_urlとsupplementary_urlsが重複 → 重複除外"""

        def decoder_side_effect(url: str) -> dict[str, object]:
            # 異なるGoogle News URLが同じ記事URLにデコードされる
            return {"status": True, "decoded_url": "https://example.com/same-article"}

        mock_decoder.side_effect = decoder_side_effect  # type: ignore[union-attr]

        extracted = ExtractedUrls(
            main_url="https://news.google.com/rss/articles/AAA",
            supplementary_urls=["https://news.google.com/rss/articles/BBB"],
        )
        result = await resolve_urls(extracted)
        assert result.main_url == "https://example.com/same-article"
        assert result.supplementary_urls == []

    @patch("slack_feed_enricher.slack.url_resolver.new_decoderv1")
    async def test_duplicate_supplementary_urls_deduplicated(self, mock_decoder: object) -> None:
        """解決後にsupplementary_urls同士が重複 → ユニーク化（順序保持）"""

        def decoder_side_effect(url: str) -> dict[str, object]:
            mapping = {
                "https://news.google.com/rss/articles/AAA": {"status": True, "decoded_url": "https://example.com/main"},
                "https://news.google.com/rss/articles/BBB": {"status": True, "decoded_url": "https://example.com/sub1"},
                "https://news.google.com/rss/articles/CCC": {"status": True, "decoded_url": "https://example.com/sub1"},
                "https://news.google.com/rss/articles/DDD": {"status": True, "decoded_url": "https://example.com/sub2"},
            }
            return mapping[url]

        mock_decoder.side_effect = decoder_side_effect  # type: ignore[union-attr]

        extracted = ExtractedUrls(
            main_url="https://news.google.com/rss/articles/AAA",
            supplementary_urls=[
                "https://news.google.com/rss/articles/BBB",
                "https://news.google.com/rss/articles/CCC",
                "https://news.google.com/rss/articles/DDD",
            ],
        )
        result = await resolve_urls(extracted)
        assert result.main_url == "https://example.com/main"
        assert result.supplementary_urls == ["https://example.com/sub1", "https://example.com/sub2"]

    async def test_non_google_news_urls_pass_through(self) -> None:
        """非Google News URLはそのまま通過する"""
        extracted = ExtractedUrls(
            main_url="https://example.com/article1",
            supplementary_urls=["https://example.com/article2"],
        )
        result = await resolve_urls(extracted)
        assert result.main_url == "https://example.com/article1"
        assert result.supplementary_urls == ["https://example.com/article2"]
