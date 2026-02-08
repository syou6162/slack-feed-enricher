from __future__ import annotations

import logging
import urllib.parse
from typing import Protocol, runtime_checkable

import aiohttp

from slack_feed_enricher.hatebu.models import HatebuBookmark, HatebuEntry

logger = logging.getLogger(__name__)

_JSONLITE_BASE_URL = "https://b.hatena.ne.jp/entry/jsonlite/"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


@runtime_checkable
class HatebuClient(Protocol):
    """はてなブックマークエントリー取得のProtocol"""

    async def fetch_entry(self, url: str) -> HatebuEntry | None: ...


class AiohttpHatebuClient:
    """aiohttp を用いた HatebuClient 実装"""

    async def fetch_entry(self, url: str) -> HatebuEntry | None:
        """URLに対応するはてなブックマークエントリーを取得する。

        404やnullレスポンス、タイムアウト時はNoneを返す。
        """
        encoded_url = urllib.parse.quote(url, safe="")
        api_url = f"{_JSONLITE_BASE_URL}?url={encoded_url}"

        try:
            async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session, session.get(api_url) as response:
                if response.status == 404:
                    return None
                if response.status != 200:
                    logger.warning("Hatena API returned status %d for URL: %s", response.status, url)
                    return None

                data = await response.json()
                if data is None:
                    return None

                bookmarks = [
                    HatebuBookmark(
                        user=b["user"],
                        comment=b.get("comment", ""),
                        timestamp=b.get("timestamp", ""),
                    )
                    for b in data.get("bookmarks", [])
                ]

                return HatebuEntry(
                    count=data.get("count", 0),
                    bookmarks=bookmarks,
                )
        except (TimeoutError, aiohttp.ClientError):
            return None
