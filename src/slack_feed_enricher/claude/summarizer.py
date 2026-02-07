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


def build_summary_prompt(url: str, supplementary_urls: list[str] | None = None) -> str:
    """要約用プロンプトを構築する

    Args:
        url: メインURL（記事本体）
        supplementary_urls: 補足URL（引用先、ツール説明等）

    Returns:
        構築されたプロンプト文字列
    """
    parts = [
        "以下のURLの内容をすべてWebFetchで取得してください。",
        "",
        f"メインURL（記事本体）: {url}",
    ]

    if supplementary_urls:
        parts.append("")
        parts.append("補足URL:")
        for sup_url in supplementary_urls:
            parts.append(f"- {sup_url}")
        parts.append("")
        parts.append(
            "メインURLが主たる情報源です。補足URLは記事内で言及されているツールや"
            "引用元の詳細情報なので、要約に適宜取り込んでください。"
        )

    parts.append("")
    parts.append("取得した内容をもとに、以下の3つのブロックに分けて出力してください。")
    parts.append("")
    parts.append("## ブロック1: メタ情報")
    parts.append("- 記事のタイトル")
    parts.append("- URL")
    parts.append("- 著者名（はてなブログID、Twitter/X ID、本名など、取得できるもの）")
    parts.append("- カテゴリー（大カテゴリー / 中カテゴリーの2階層）")
    parts.append("  例: データエンジニアリング / BigQuery")
    parts.append("- 記事の投稿日時")
    parts.append("")
    parts.append("## ブロック2: 簡潔な要約")
    parts.append("- 箇条書きで最大5行")
    parts.append("- 記事の核心を簡潔にまとめる")
    parts.append("")
    parts.append("## ブロック3: 詳細")
    parts.append("- 記事の内容を構造化して詳細に説明")
    parts.append("- 要約ではなく、記事の内容を網羅的に記述")
    parts.append("- ただし、Slack APIのメッセージ長制限（40,000文字）を考慮し、適度な長さに収める")

    return "\n".join(parts)


async def fetch_and_summarize(
    query_func: QueryFunc,
    url: str,
) -> str:
    """URLの内容をWebFetchで取得し、markdown形式で要約する

    Args:
        query_func: claude_agent_sdk.query関数（またはモック）
        url: 要約対象のURL

    Returns:
        markdown形式の要約テキスト

    Raises:
        ValueError: URLが空の場合
        NoResultMessageError: ResultMessageが取得できなかった場合
        ClaudeAPIError: Claude APIでエラーが発生した場合
        StructuredOutputError: 構造化出力が取得できなかった場合
    """
    if not url:
        raise ValueError("URLが空です")

    # プロンプト構築
    prompt = f"""{url} の内容をWebFetchで取得し、要約してください。

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
