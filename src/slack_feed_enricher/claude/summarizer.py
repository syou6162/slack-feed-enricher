"""Claude Agent SDKを使用したURL要約機能"""

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from slack_feed_enricher.claude.exceptions import (
    ClaudeAPIError,
    NoResultMessageError,
    StructuredOutputError,
)

logger = logging.getLogger(__name__)

QueryFunc = Callable[..., AsyncIterator[Any]]

# 構造化出力スキーマ
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "markdown": {"type": "string", "description": "Slackスレッドに投稿するmarkdown形式の整形済みテキスト"}
        },
        "required": ["markdown"]
    }
}


async def fetch_and_summarize(
    query_func: QueryFunc,
    urls: list[str],
) -> str:
    """URLリストの内容をWebFetchで取得し、markdown形式で要約する

    Args:
        query_func: claude_agent_sdk.query関数（またはモック）
        urls: 要約対象のURLリスト

    Returns:
        markdown形式の要約テキスト

    Raises:
        ValueError: URLリストが空の場合
        NoResultMessageError: ResultMessageが取得できなかった場合
        ClaudeAPIError: Claude APIでエラーが発生した場合
        StructuredOutputError: 構造化出力が取得できなかった場合
    """
    if not urls:
        raise ValueError("URLリストが空です")

    # プロンプト構築
    url_list = "\n".join(f"- {url}" for url in urls)
    prompt = f"""以下のURLの内容をWebFetchで取得し、要約してください。

URL:
{url_list}

要約はmarkdown形式で、以下を含めてください:
- 記事のタイトル
- 主要なポイント（箇条書き）
- 一言まとめ
"""

    # ClaudeAgentOptions作成
    options = ClaudeAgentOptions(
        output_format=OUTPUT_SCHEMA,
        permission_mode="acceptEdits",
        allowed_tools=["WebFetch", "WebSearch"],
    )

    # query実行
    result_message: ResultMessage | None = None
    async for message in query_func(prompt=prompt, options=options):
        logger.info(f"Received message: {type(message).__name__} - {message}")
        if isinstance(message, ResultMessage):
            result_message = message

    if result_message is None:
        raise NoResultMessageError("ResultMessageが取得できませんでした")

    if result_message.is_error:
        raise ClaudeAPIError("要約処理でエラーが発生しました", result_message.result)

    if result_message.structured_output is None:
        raise StructuredOutputError("構造化出力が取得できませんでした")

    return result_message.structured_output["markdown"]
