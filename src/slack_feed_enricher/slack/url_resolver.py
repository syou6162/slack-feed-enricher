"""Google News URL解決モジュール"""

import asyncio
import logging
from urllib.parse import urlparse

from googlenewsdecoder import new_decoderv1

from slack_feed_enricher.slack.url_extractor import ExtractedUrls

logger = logging.getLogger(__name__)

_DECODE_TIMEOUT_SECONDS = 10


def is_google_news_url(url: str) -> bool:
    """URLがGoogle Newsの/rss/articles/形式かどうかを判定する。

    /topics/や/topstories等のデコード不可なURLは除外する。
    """
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.hostname == "news.google.com" and "/rss/articles/" in parsed.path


async def resolve_url(url: str) -> str:
    """Google News URLを実際の記事URLにデコードする。

    非Google News URLはそのまま返す。
    デコード失敗・タイムアウト時は元URLをフォールバックする。
    """
    if not is_google_news_url(url):
        return url

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(new_decoderv1, url),
            timeout=_DECODE_TIMEOUT_SECONDS,
        )
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
        logger.warning("Google News URLのデコード失敗 (status=False): %s", url)
        return url
    except TimeoutError:
        logger.warning("Google News URLのデコードがタイムアウトしました: %s", url)
        return url
    except Exception:
        logger.warning("Google News URLのデコード中に例外が発生しました: %s", url, exc_info=True)
        return url


async def resolve_urls(extracted: ExtractedUrls) -> ExtractedUrls:
    """ExtractedUrlsのmain_urlとsupplementary_urlsを両方解決する。

    解決後にsupplementary_urlsからmain_urlと重複するURLを除外し、
    supplementary_urls同士の重複も除外する（順序保持）。
    """
    if extracted.main_url is None:
        return extracted

    resolved_main = await resolve_url(extracted.main_url)

    resolved_supplementary: list[str] = []
    for url in extracted.supplementary_urls:
        resolved_supplementary.append(await resolve_url(url))

    # 重複排除: main_urlとの重複 + supplementary_urls同士の重複（順序保持）
    seen: set[str] = {resolved_main}
    unique_supplementary: list[str] = []
    for url in resolved_supplementary:
        if url not in seen:
            seen.add(url)
            unique_supplementary.append(url)

    return ExtractedUrls(main_url=resolved_main, supplementary_urls=unique_supplementary)
