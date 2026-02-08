"""URL解決機能のテスト"""

from slack_feed_enricher.slack.url_resolver import is_google_news_url


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
