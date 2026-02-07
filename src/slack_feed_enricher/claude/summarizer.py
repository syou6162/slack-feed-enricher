"""Claude Agent SDKを使用したURL要約機能"""

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from slack_feed_enricher.claude.exceptions import (
    ClaudeAPIError,
    NoResultMessageError,
    StructuredOutputError,
)
from slack_feed_enricher.slack.blocks import SlackBlock, SlackSectionBlock, SlackTextObject

logger = logging.getLogger(__name__)

QueryFunc = Callable[..., AsyncIterator[Any]]


class Meta(BaseModel):
    model_config = ConfigDict(json_schema_extra=None)
    title: str
    url: str
    author: str | None
    category_large: str | None
    category_medium: str | None
    published_at: str | None


class Summary(BaseModel):
    points: list[str] = Field(min_length=1, max_length=5)


class StructuredOutput(BaseModel):
    meta: Meta
    summary: Summary
    detail: str


class EnrichResult(BaseModel, frozen=True):
    meta_blocks: list[SlackBlock]
    meta_text: str
    summary_blocks: list[SlackBlock]
    summary_text: str
    detail_text: str


# 構造化出力スキーマ
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": StructuredOutput.model_json_schema(),
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
        "以下のURLをWebFetchで取得し、次の項目を抽出してください。",
        "",
        "抽出項目:",
        "- meta.title: 記事のタイトル",
        "- meta.url: 記事のURL",
        "- meta.author: 著者名（はてなID、Twitter/X ID、本名など。不明ならnull）",
        "- meta.category_large: 大カテゴリー（例: データエンジニアリング。不明ならnull）",
        "- meta.category_medium: 中カテゴリー（例: BigQuery。不明ならnull）",
        "- meta.published_at: 投稿日時（ISO 8601形式。不明ならnull）",
        "- summary.points: 記事の核心を簡潔にまとめた箇条書き（1〜5項目）",
        "- detail: 記事内容を構造化した詳細説明（markdown形式）",
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


def build_meta_blocks(meta: Meta) -> list[SlackBlock]:
    """MetaモデルからSlack Block Kitブロック配列を生成する

    Args:
        meta: Metaモデルインスタンス

    Returns:
        SlackBlockのリスト（sectionブロック1つ）
    """
    text = format_meta_block(meta.model_dump())
    return [SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text=text))]


def build_summary_blocks(summary: Summary) -> list[SlackBlock]:
    """SummaryモデルからSlack Block Kitブロック配列を生成する

    Args:
        summary: Summaryモデルインスタンス

    Returns:
        SlackBlockのリスト（sectionブロック1つ）
    """
    text = format_summary_block(summary.model_dump())
    return [SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text=text))]


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
) -> EnrichResult:
    """URLの内容をWebFetchで取得し、構造化された要約結果を返す

    Args:
        query_func: claude_agent_sdk.query関数（またはモック）
        url: 要約対象のURL
        supplementary_urls: 補足URL（引用先、ツール説明等）

    Returns:
        EnrichResult: Block Kit形式のブロックとフォールバックテキストを含む結果

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

    # dict→Pydanticモデル変換（ValidationErrorはStructuredOutputErrorに変換）
    try:
        parsed = StructuredOutput.model_validate(so)
    except ValidationError as e:
        raise StructuredOutputError(f"構造化出力のバリデーションに失敗しました: {e}") from e

    meta_text = format_meta_block(parsed.meta.model_dump())
    summary_text = format_summary_block(parsed.summary.model_dump())

    return EnrichResult(
        meta_blocks=build_meta_blocks(parsed.meta),
        meta_text=meta_text,
        summary_blocks=build_summary_blocks(parsed.summary),
        summary_text=summary_text,
        detail_text=parsed.detail,
    )
