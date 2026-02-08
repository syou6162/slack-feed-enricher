"""Google News URL解決モジュール"""

from urllib.parse import urlparse


def is_google_news_url(url: str) -> bool:
    """URLがGoogle Newsの/rss/articles/形式かどうかを判定する。

    /topics/や/topstories等のデコード不可なURLは除外する。
    """
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.hostname == "news.google.com" and "/rss/articles/" in parsed.path
