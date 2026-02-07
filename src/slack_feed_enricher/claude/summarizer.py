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
            "meta": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "記事のタイトル"},
                    "url": {"type": "string", "format": "uri", "description": "記事のURL"},
                    "author": {"type": ["string", "null"], "description": "著者名（はてなID、Twitter/X ID、本名など。取得できない場合はnull）"},
                    "category_large": {"type": ["string", "null"], "description": "大カテゴリー（例: データエンジニアリング。判定できない場合はnull）"},
                    "category_medium": {"type": ["string", "null"], "description": "中カテゴリー（例: BigQuery。判定できない場合はnull）"},
                    "published_at": {"type": ["string", "null"], "format": "date-time", "description": "記事の投稿日時（ISO 8601形式。取得できない場合はnull）"},
                },
                "required": ["title", "url", "author", "category_large", "category_medium", "published_at"],
            },
            "summary": {
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 5,
                        "description": "記事の核心を簡潔にまとめた箇条書き（最大5項目）",
                    }
                },
                "required": ["points"],
            },
            "detail": {"type": "string", "description": "記事内容を構造化した詳細説明（markdown形式）"},
        },
        "required": ["meta", "summary", "detail"],
    },
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

    return "\n".join(parts)


def format_meta_block(meta: dict[str, Any]) -> str:
    """メタ情報ブロックをフォーマットする

    Args:
        meta: メタ情報辞書（title, url, author, category_large, category_medium, published_at）

    Returns:
        フォーマットされたメタ情報文字列
    """
    lines = []
    lines.append(f"*{meta['title']}*")
    lines.append(f"URL: {meta['url']}")
    lines.append(f"著者: {meta['author'] or '不明'}")

    category_large = meta.get("category_large")
    category_medium = meta.get("category_medium")
    if category_large and category_medium:
        lines.append(f"カテゴリー: {category_large} / {category_medium}")
    elif category_large:
        lines.append(f"カテゴリー: {category_large}")
    elif category_medium:
        lines.append(f"カテゴリー: {category_medium}")
    else:
        lines.append("カテゴリー: 不明")

    lines.append(f"投稿日時: {meta['published_at'] or '不明'}")

    return "\n".join(lines)


def format_summary_block(summary: dict[str, Any]) -> str:
    """簡潔な要約ブロックをフォーマットする

    Args:
        summary: 要約辞書（points: list[str]）

    Returns:
        フォーマットされた箇条書き文字列
    """
    return "\n".join(f"- {point}" for point in summary["points"])


async def fetch_and_summarize(
    query_func: QueryFunc,
    url: str,
    supplementary_urls: list[str] | None = None,
) -> list[str]:
    """URLの内容をWebFetchで取得し、3ブロック構造で要約する

    Args:
        query_func: claude_agent_sdk.query関数（またはモック）
        url: 要約対象のURL
        supplementary_urls: 補足URL（引用先、ツール説明等）

    Returns:
        3つのブロック文字列のリスト [メタ情報, 簡潔な要約, 詳細]

    Raises:
        ValueError: URLが空の場合
        NoResultMessageError: ResultMessageが取得できなかった場合
        ClaudeAPIError: Claude APIでエラーが発生した場合
        StructuredOutputError: 構造化出力が取得できなかった場合
    """
    if not url:
        raise ValueError("URLが空です")

    # プロンプト構築
    prompt = build_summary_prompt(url, supplementary_urls)

    # ClaudeAgentOptions作成
    options = ClaudeAgentOptions(
        output_format=OUTPUT_SCHEMA,
        permission_mode="acceptEdits",
        allowed_tools=["WebFetch", "WebSearch"],
        max_turns=10,
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
        raise StructuredOutputError(
            f"構造化出力が取得できませんでした (subtype={result_message.subtype}, result={result_message.result})"
        )

    so = result_message.structured_output

    # キー欠損チェック
    required_keys = ["meta", "summary", "detail"]
    missing_keys = [key for key in required_keys if key not in so]
    if missing_keys:
        raise StructuredOutputError(
            f"構造化出力に必要なキーが欠損しています: {', '.join(missing_keys)}"
        )

    return [format_meta_block(so["meta"]), format_summary_block(so["summary"]), so["detail"]]
