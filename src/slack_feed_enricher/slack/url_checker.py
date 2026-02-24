"""URLの到達可能性チェックモジュール"""

from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)

# LLMに投げず即スキップする恒久失敗ステータスコード
PERMANENT_FAILURE_STATUSES: frozenset[int] = frozenset({403, 404, 410})

_DEFAULT_TIMEOUT_SECONDS = 10.0


async def check_url_status(url: str, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> int | None:
    """URLにHTTP HEADリクエストを送り、ステータスコードを返す。

    接続エラーやタイムアウトの場合はNoneを返す（楽観的にLLMに渡す）。

    Args:
        url: チェック対象のURL
        timeout_seconds: タイムアウト秒数

    Returns:
        HTTPステータスコード。接続エラー/タイムアウト時はNone。
    """
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with aiohttp.ClientSession() as session, session.head(url, allow_redirects=True, timeout=timeout) as response:
            return response.status
    except (TimeoutError, aiohttp.ClientError) as e:
        logger.debug("URL status check failed for %s: %r", url, e)
        return None
