"""Claude Agent SDKを使用したURL要約機能"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from claude_agent_sdk._errors import MessageParseError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from slack_feed_enricher.claude.exceptions import (
    ClaudeAPIError,
    NoResultMessageError,
    QueryTimeoutError,
    StructuredOutputError,
)
from slack_feed_enricher.hatebu.models import HatebuEntry
from slack_feed_enricher.slack.blocks import (
    SlackBlock,
    SlackContextBlock,
    SlackContextElement,
    SlackDividerBlock,
    SlackHeaderBlock,
    SlackRichTextBlock,
    SlackRichTextList,
    SlackRichTextSection,
    SlackSectionBlock,
    SlackTextElement,
    SlackTextObject,
)
from slack_feed_enricher.slack.markdown_converter import convert_markdown_to_mrkdwn

logger = logging.getLogger(__name__)

QueryFunc = Callable[..., AsyncIterator[Any]]


class AuthorProfile(BaseModel):
    """著者プロフィール情報

    記事を読む価値があるかを人が判断する際の補助として表示する。
    """

    name: str | None
    expertise_areas: list[str]
    evidence_urls: list[str]


class Meta(BaseModel):
    model_config = ConfigDict(json_schema_extra=None)
    title: str
    url: str
    author: AuthorProfile | None
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
    blocks: list[SlackBlock]
    fallback_text: str


# 構造化出力スキーマ
OUTPUT_SCHEMA = {
    "type": "json_schema",
    "schema": StructuredOutput.model_json_schema(),
}

_AUTHOR_COLLECTION_INSTRUCTIONS = """\
著者情報の収集:
- 元記事ページから著者名・プロフィールリンクを探す
- 著者名やユーザーIDが判明したら、必ずプロフィールページをWebFetchで取得し、
  自己紹介文・投稿履歴・所属情報から専門領域を推定する
- プラットフォーム別のプロフィールURL構築パターン:
  - Qiita: https://qiita.com/{ユーザーID} → 自己紹介・投稿一覧から専門領域を確認
  - Zenn: https://zenn.dev/{ユーザーID} → プロフィール・投稿傾向を確認
  - はてなブログ: ブログURL + /about → Aboutページから著者情報を確認
  - note: https://note.com/{ユーザーID} → プロフィールページを確認
  - Medium: https://medium.com/@{ユーザーID} → プロフィールを確認
  - GitHub: https://github.com/{ユーザーID} → READMEやbioから専門領域を確認
  - Speaker Deck / SlideShare: 発表資料から専門領域を推定
  - 個人サイト / 技術ブログ: /about や /profile ページを探す
- プロフィールページで確認すべき情報:
  - 自己紹介文（所属企業・役職・専門分野）
  - 投稿記事のタイトル一覧（頻出トピックから専門領域を推定）
  - SNSリンク（Twitter/X等のbioも参考になる）
- evidence_urlsには実際にWebFetchで取得したプロフィールページのURLを記録する
- 著者情報が見つからない場合はmeta.authorをnullとする"""


def build_summary_prompt(
    url: str,
    supplementary_urls: list[str] | None = None,
    hatebu_entry: HatebuEntry | None = None,
) -> str:
    """要約用プロンプトを構築する

    Args:
        url: メインURL（記事本体）
        supplementary_urls: 補足URL（引用先、ツール説明等）
        hatebu_entry: はてなブックマークエントリー情報（Noneなら省略）

    Returns:
        構築されたプロンプト文字列
    """
    prompt = f"""\
以下のURLをWebFetchで取得し、次の項目を抽出してください。

抽出項目:
- meta.title: 記事のタイトル
- meta.url: 記事のURL
- meta.author: 著者プロフィール情報（取得できなければnull）
  - meta.author.name: 著者名（はてなID、Twitter/X ID、本名など。不明ならnull）
  - meta.author.expertise_areas: 著者の専門領域の推定（例: ["インフラ", "Terraform", "AWS"]）
  - meta.author.evidence_urls: 著者プロフィールページやAboutページ等のURL
- meta.category_large: 大カテゴリー（例: データエンジニアリング。不明ならnull）
- meta.category_medium: 中カテゴリー（例: BigQuery。不明ならnull）
- meta.published_at: 投稿日時（ISO 8601形式。不明ならnull）
- summary.points: 記事の核心を簡潔にまとめた箇条書き（1〜5項目）
- detail: 記事内容を構造化した詳細説明（markdown形式）

メインURL（記事本体）: {url}

{_AUTHOR_COLLECTION_INSTRUCTIONS}"""

    if supplementary_urls:
        urls_list = "\n".join(f"- {sup_url}" for sup_url in supplementary_urls)
        prompt += f"""

補足URL:
{urls_list}

メインURLが主たる情報源です。補足URLは記事内で言及されているツールや\
引用元の詳細情報なので、要約に適宜取り込んでください。"""

    if hatebu_entry is not None and hatebu_entry.comment_count > 0:
        filepath = _write_hatebu_comments_to_file(hatebu_entry)
        if filepath:
            prompt += f"""

以下のファイルにはてなブックマークコメントがあります：
{filepath}

記事要約の際にこれらのコメントも参考にしてください。"""

    return prompt


_HATEBU_COMMENTS_FILE = ".hatena_bookmark/hatebu_comments.txt"


def _write_hatebu_comments_to_file(entry: HatebuEntry) -> str:
    """はてブコメントをファイルに出力し、ファイルパスを返す。

    コメント付きブックマークが0件の場合は空文字列を返す。
    ファイル書き込みに失敗した場合も空文字列を返す（フェイルオープン）。
    """
    comments = entry.comments
    if not comments:
        return ""

    try:
        filepath = Path(_HATEBU_COMMENTS_FILE)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# はてなブックマークコメント\n\n")
            for bookmark in comments:
                f.write(f"- **{bookmark.user}**: {bookmark.comment}\n")
    except OSError:
        logger.warning("はてブコメントファイルの書き込みに失敗しました: %s", _HATEBU_COMMENTS_FILE)
        return ""

    return _HATEBU_COMMENTS_FILE


def build_meta_blocks(meta: Meta, hatebu_entry: HatebuEntry | None = None) -> list[SlackBlock]:
    """MetaモデルからSlack Block Kitブロック配列を生成する

    titleをSlackHeaderBlockで表示（summary/detailと統一）し、
    メタデータ属性はfieldsで2列表示する。URLは必須フィールドとして常に含む。

    Args:
        meta: Metaモデルインスタンス
        hatebu_entry: はてなブックマークエントリー情報（Noneなら省略）

    Returns:
        SlackBlockのリスト（headerブロック + fields section）
    """
    # Slackのheaderブロックは最大150文字
    truncated_title = meta.title[:150] if len(meta.title) > 150 else meta.title
    header_block = SlackHeaderBlock(text=SlackTextObject(type="plain_text", text=truncated_title))

    fields: list[SlackTextObject] = [
        SlackTextObject(type="mrkdwn", text="*URL*"),
        SlackTextObject(type="mrkdwn", text=f"<{meta.url}>"),
    ]
    if meta.author and meta.author.name:
        author_text = meta.author.name
        if meta.author.expertise_areas:
            author_text += f" ({', '.join(meta.author.expertise_areas)})"
        fields.extend([
            SlackTextObject(type="mrkdwn", text="*Author*"),
            SlackTextObject(type="plain_text", text=author_text),
        ])
    if meta.category_large and meta.category_medium:
        fields.extend([
            SlackTextObject(type="mrkdwn", text="*Category*"),
            SlackTextObject(type="plain_text", text=f"{meta.category_large} / {meta.category_medium}"),
        ])
    elif meta.category_large:
        fields.extend([
            SlackTextObject(type="mrkdwn", text="*Category*"),
            SlackTextObject(type="plain_text", text=meta.category_large),
        ])
    elif meta.category_medium:
        fields.extend([
            SlackTextObject(type="mrkdwn", text="*Category*"),
            SlackTextObject(type="plain_text", text=meta.category_medium),
        ])
    if meta.published_at:
        fields.extend([
            SlackTextObject(type="mrkdwn", text="*Published*"),
            SlackTextObject(type="plain_text", text=meta.published_at),
        ])
    if hatebu_entry is not None:
        fields.extend([
            SlackTextObject(type="mrkdwn", text="*Hatena Bookmark*"),
            SlackTextObject(type="plain_text", text=f"\U0001f4da {hatebu_entry.count} users / \U0001f4ac {hatebu_entry.comment_count} comments"),
        ])

    metadata_section = SlackSectionBlock(fields=fields)
    return [header_block, metadata_section]


def build_summary_blocks(summary: Summary) -> list[SlackBlock]:
    """SummaryモデルからSlack Block Kitブロック配列を生成する

    SlackHeaderBlockで「Summary」タイトルを表示し、rich_text_listでネイティブ箇条書きを表示する。

    Args:
        summary: Summaryモデルインスタンス

    Returns:
        SlackBlockのリスト（headerブロック + rich_textブロック）
    """
    header_block = SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="Summary"))
    list_items = [
        SlackRichTextSection(elements=[SlackTextElement(text=point)])
        for point in summary.points
    ]
    rich_text_block = SlackRichTextBlock(
        elements=[SlackRichTextList(style="bullet", elements=list_items)]
    )
    return [header_block, rich_text_block]


def _find_code_block_ranges(text: str) -> list[tuple[int, int]]:
    """テキスト内のコードブロック(```)の範囲を返す。

    Returns:
        (start, end)のリスト。startは開始```の位置、endは閉じ```+3の位置。
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    while pos < len(text):
        start = text.find("```", pos)
        if start == -1:
            break
        end = text.find("```", start + 3)
        if end == -1:
            # 閉じがない場合はテキスト末尾まで
            ranges.append((start, len(text)))
            break
        ranges.append((start, end + 3))
        pos = end + 3
    return ranges


def _is_inside_code_block(pos: int, code_ranges: list[tuple[int, int]]) -> bool:
    """指定位置がコードブロック内かどうかを判定する。"""
    return any(start <= pos < end for start, end in code_ranges)


def _is_inside_slack_link(text: str, pos: int) -> bool:
    """指定位置がSlackリンク<url|text>の内部かどうかを判定する。"""
    # posより前の最後の < を探す
    last_open = text.rfind("<", 0, pos)
    if last_open == -1:
        return False
    # その < に対応する > がpos以降にあるか
    next_close = text.find(">", last_open)
    return next_close >= pos


def _find_safe_newline(remaining: str, max_length: int, code_ranges: list[tuple[int, int]], offset: int) -> int:
    """コードブロック外の改行位置を探す。

    Args:
        remaining: 分割対象テキスト
        max_length: 最大長
        code_ranges: コードブロックの範囲（元テキスト基準）
        offset: remainingの元テキスト内でのオフセット

    Returns:
        改行位置。見つからなければ-1。
    """
    search_end = min(max_length, len(remaining))
    pos = search_end
    while pos > 0:
        pos = remaining.rfind("\n", 0, pos)
        if pos <= 0:
            return -1
        # コードブロック内の改行は使わない
        abs_pos = offset + pos
        if not _is_inside_code_block(abs_pos, code_ranges):
            return pos
        pos -= 1
    return -1


def _adjust_split_for_slack_link(remaining: str, split_pos: int, max_length: int, reopen_cost: int) -> int:
    """Slackリンクの途中で分割しないよう分割位置を調整する。

    Args:
        remaining: 分割対象テキスト
        split_pos: 現在の分割候補位置
        max_length: 1チャンクの最大文字数
        reopen_cost: コードブロック再オープンのコスト

    Returns:
        調整後の分割位置
    """
    if not _is_inside_slack_link(remaining, split_pos):
        return split_pos

    link_start = remaining.rfind("<", 0, split_pos)
    if link_start < 0:
        return split_pos

    if link_start > 0:
        return link_start

    # リンクがチャンク先頭（位置0）の場合、リンク全体を含める
    link_end = remaining.find(">", split_pos)
    if link_end >= 0:
        link_whole = min(link_end + 1, len(remaining))
        if link_whole + reopen_cost <= max_length:
            return link_whole

    # リンク全体がmax_lengthを超える場合は強制分割
    return split_pos


def _split_mrkdwn_text(text: str, max_length: int = 3000) -> list[str]:
    """mrkdwnテキストを構文を壊さないように分割する。

    改行位置での分割を優先し、コードブロック内の改行は分割に使わない。
    コードブロックが境界をまたぐ場合は閉じて次チャンクで再オープンする。
    Slackリンク(<url|text>)の途中では分割しない。
    &amp;/&lt;/&gt;エンティティの途中では分割しない。

    Args:
        text: 分割対象テキスト
        max_length: 1チャンクの最大文字数

    Returns:
        分割されたテキストのリスト
    """
    if len(text) <= max_length:
        return [text]

    code_ranges = _find_code_block_ranges(text)
    chunks: list[str] = []
    remaining = text
    offset = 0
    in_code_block = False

    fence_len = 4  # "```\n" or "\n```" = 4文字

    while remaining:
        # コードブロック内にいる場合は再オープン(```\n)と閉じフェンス(\n```)の両方を考慮
        # コードブロック外でも、分割先がコードブロック内に入る可能性があるため
        # 閉じフェンス分は強制分割パスで個別に考慮する
        reopen_cost = fence_len if in_code_block else 0
        effective_max = max_length - reopen_cost

        if len(remaining) <= effective_max:
            chunks.append(("```\n" if in_code_block else "") + remaining)
            break

        # コードブロック外の改行位置での分割を試みる
        newline_pos = _find_safe_newline(remaining, effective_max, code_ranges, offset)
        if newline_pos > 0:
            chunk_text = remaining[:newline_pos]
            if in_code_block:
                chunk_text = "```\n" + chunk_text
                in_code_block = False
            chunks.append(chunk_text)
            remaining = remaining[newline_pos + 1:]
            offset += newline_pos + 1
            continue

        # 改行がない場合の強制分割
        # コードブロック内で分割する場合は閉じフェンス分も差し引く
        will_split_in_code = _is_inside_code_block(
            offset + min(effective_max, len(remaining)),
            code_ranges,
        )
        close_cost = fence_len if will_split_in_code else 0
        split_pos = effective_max - close_cost

        # Slackリンクの途中を避ける
        split_pos = _adjust_split_for_slack_link(remaining, split_pos, max_length, reopen_cost)

        # エンティティの途中を避ける
        split_pos = _adjust_for_entity_boundary(remaining, split_pos)

        # 調整後のsplit_posでコードブロック内かどうかを再判定
        will_split_in_code = _is_inside_code_block(offset + split_pos, code_ranges)

        chunk_text = remaining[:split_pos]

        # コードブロック内で分割する場合の処理
        if will_split_in_code:
            if in_code_block:
                chunk_text = "```\n" + chunk_text
            chunk_text = chunk_text + "\n```"
            in_code_block = True
        elif in_code_block:
            chunk_text = "```\n" + chunk_text
            in_code_block = False

        chunks.append(chunk_text)
        remaining = remaining[split_pos:]
        offset += split_pos

    return chunks


def _adjust_for_entity_boundary(text: str, pos: int) -> int:
    """エンティティ(&amp; &lt; &gt;)の途中で分割しないよう位置を調整する。

    Args:
        text: テキスト
        pos: 分割候補位置

    Returns:
        調整後の分割位置
    """
    # pos付近で&が始まるエンティティをチェック
    # 最大エンティティ長は &amp; の5文字
    for offset in range(5):
        check_pos = pos - offset
        if check_pos < 0:
            break
        if check_pos >= len(text):
            continue
        if text[check_pos] == "&":
            # この&から始まるエンティティがposをまたぐかチェック
            for entity in ("&amp;", "&lt;", "&gt;"):
                if text[check_pos:check_pos + len(entity)] == entity:
                    entity_end = check_pos + len(entity)
                    if entity_end > pos:
                        # エンティティの前で分割
                        return check_pos
    return pos


def build_detail_blocks(detail: str) -> list[SlackBlock]:
    """detail文字列からSlack Block Kitブロック配列を生成する

    SlackHeaderBlockで「Details」タイトルを表示し、Markdown→mrkdwn変換後の
    detailテキストをsectionブロックで表示する。
    3000文字を超える場合は改行位置を優先して複数sectionに分割する。

    Args:
        detail: 詳細テキスト（markdown形式）

    Returns:
        SlackBlockのリスト（headerブロック + 1つ以上のsectionブロック）
    """
    header_block = SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="Details"))

    # Markdown→Slack mrkdwn変換
    converted = convert_markdown_to_mrkdwn(detail)

    # 3000文字以下ならそのまま
    chunks = _split_mrkdwn_text(converted)

    sections: list[SlackBlock] = [header_block]
    for chunk in chunks:
        sections.append(SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text=chunk)))

    return sections


def _build_context_elements(meta: Meta, hatebu_entry: HatebuEntry | None = None) -> list[SlackContextElement]:
    """MetaモデルからContextブロック用のelementsを生成する"""
    parts: list[str] = []
    if meta.author and meta.author.name:
        author_text = meta.author.name
        if meta.author.expertise_areas:
            author_text += f" ({', '.join(meta.author.expertise_areas)})"
        parts.append(f"著者: {author_text}")
    if meta.category_large and meta.category_medium:
        parts.append(f"{meta.category_large} / {meta.category_medium}")
    elif meta.category_large:
        parts.append(meta.category_large)
    elif meta.category_medium:
        parts.append(meta.category_medium)
    if meta.published_at:
        parts.append(meta.published_at)
    if hatebu_entry is not None:
        parts.append(f"\U0001f4da {hatebu_entry.count} users / \U0001f4ac {hatebu_entry.comment_count} comments")
    return [SlackContextElement(type="mrkdwn", text=" | ".join(parts))] if parts else []


def build_unified_blocks(
    meta: Meta,
    summary: Summary,
    detail: str,
    hatebu_entry: HatebuEntry | None = None,
) -> list[SlackBlock]:
    """統合された1メッセージ用のBlock Kit配列を生成する

    レイアウト:
    1. Header: 記事タイトル
    2. Context: 著者 / カテゴリ / 公開日 / はてブ数
    3. Section: 元記事URL
    4. Divider
    5. RichText (bullet list): 要約
    6. Divider
    7. Section × N: 詳細 (3000文字分割)

    Args:
        meta: Metaモデルインスタンス
        summary: Summaryモデルインスタンス
        detail: 詳細テキスト（markdown形式、はてブコメント結合済み）
        hatebu_entry: はてなブックマークエントリー情報（Noneなら省略）

    Returns:
        SlackBlockのリスト
    """
    blocks: list[SlackBlock] = []

    # 1. Header: 記事タイトル
    truncated_title = meta.title[:150] if len(meta.title) > 150 else meta.title
    blocks.append(SlackHeaderBlock(text=SlackTextObject(type="plain_text", text=truncated_title)))

    # 2. Context: 著者 / カテゴリ / 公開日 / はてブ数
    context_elements = _build_context_elements(meta, hatebu_entry)
    if context_elements:
        blocks.append(SlackContextBlock(elements=context_elements))

    # 3. Section: 元記事URL
    blocks.append(SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text=f"<{meta.url}>")))

    # 4. Divider
    blocks.append(SlackDividerBlock())

    # 5. RichText (bullet list): 要約
    list_items = [
        SlackRichTextSection(elements=[SlackTextElement(text=point)])
        for point in summary.points
    ]
    blocks.append(SlackRichTextBlock(
        elements=[SlackRichTextList(style="bullet", elements=list_items)]
    ))

    # 6. Divider
    blocks.append(SlackDividerBlock())

    # 7. Section × N: 詳細 (3000文字分割)
    converted = convert_markdown_to_mrkdwn(detail)
    chunks = _split_mrkdwn_text(converted)
    for chunk in chunks:
        blocks.append(SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text=chunk)))

    return blocks


def build_fallback_text(
    meta: Meta,
    summary: Summary,
    hatebu_entry: HatebuEntry | None = None,
) -> str:
    """通知用のフォールバックテキストを生成する

    Args:
        meta: Metaモデルインスタンス
        summary: Summaryモデルインスタンス
        hatebu_entry: はてなブックマークエントリー情報（Noneなら省略）

    Returns:
        フォールバックテキスト文字列
    """
    lines: list[str] = []
    lines.append(f"*{meta.title}*")
    author_name = meta.author.name if meta.author else None
    lines.append(f"著者: {author_name or '不明'}")

    if hatebu_entry is not None:
        lines.append(f"はてブ: {hatebu_entry.count} users")

    lines.append("")
    lines.append("要約:")
    for point in summary.points:
        lines.append(f"- {point}")

    return "\n".join(lines)


def format_meta_block(meta: dict[str, Any], hatebu_entry: HatebuEntry | None = None) -> str:
    """メタ情報ブロックをフォーマットする

    Args:
        meta: メタ情報辞書（title, url, author, category_large, category_medium, published_at）
        hatebu_entry: はてなブックマークエントリー情報（Noneなら省略）

    Returns:
        フォーマットされたメタ情報文字列
    """
    lines = []
    lines.append(f"*{meta['title']}*")
    lines.append(f"URL: {meta['url']}")
    author = meta.get("author")
    if isinstance(author, dict):
        author_name = author.get("name")
    elif isinstance(author, AuthorProfile):
        author_name = author.name
    else:
        author_name = author
    lines.append(f"著者: {author_name or '不明'}")

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

    if hatebu_entry is not None:
        lines.append(f"はてなブックマーク: {hatebu_entry.count} users / {hatebu_entry.comment_count} comments")

    return "\n".join(lines)


def format_summary_block(summary: dict[str, Any]) -> str:
    """簡潔な要約ブロックをフォーマットする

    Args:
        summary: 要約辞書（points: list[str]）

    Returns:
        フォーマットされた箇条書き文字列
    """
    return "\n".join(f"- {point}" for point in summary["points"])


_DETAIL_TEXT_MAX_CHARS = 40000


def _build_hatebu_comments_for_detail(entry: HatebuEntry, remaining_chars: int) -> str:
    """detail用のはてブコメントMarkdownセクションを構築する。

    コメント付きブックマークが0件の場合は空文字列を返す。
    remaining_charsを超えないようにコメント単位で打ち切る。
    """
    comments = entry.comments
    if not comments:
        return ""

    header = "\n\n## はてなブックマークコメント\n"
    total_chars = len(header)
    if total_chars > remaining_chars:
        return ""

    lines = [header]
    for bookmark in comments:
        line = f"- **{bookmark.user}**: {bookmark.comment}\n"
        if total_chars + len(line) > remaining_chars:
            break
        lines.append(line)
        total_chars += len(line)

    if len(lines) == 1:
        return ""

    return "".join(lines).rstrip("\n")


async def fetch_and_summarize(
    query_func: QueryFunc,
    url: str,
    supplementary_urls: list[str] | None = None,
    hatebu_entry: HatebuEntry | None = None,
    timeout_seconds: float | None = 300.0,
) -> EnrichResult:
    """URLの内容をWebFetchで取得し、構造化された要約結果を返す

    Args:
        query_func: claude_agent_sdk.query関数（またはモック）
        url: 要約対象のURL
        supplementary_urls: 補足URL（引用先、ツール説明等）
        hatebu_entry: はてなブックマークエントリー情報（Noneなら省略）
        timeout_seconds: query()全体のタイムアウト秒数（Noneなら無制限、0以下は不可）

    Returns:
        EnrichResult: Block Kit形式のブロックとフォールバックテキストを含む結果

    Raises:
        ValueError: URLが空の場合、またはtimeout_secondsが0以下の場合
        QueryTimeoutError: query()がtimeout_seconds秒以内に完了しなかった場合
        NoResultMessageError: ResultMessageが取得できなかった場合
        ClaudeAPIError: Claude APIでエラーが発生した場合
        StructuredOutputError: 構造化出力が取得できなかった場合
    """
    # 前回のコメントファイルを削除
    Path(_HATEBU_COMMENTS_FILE).unlink(missing_ok=True)

    if not url:
        raise ValueError("URLが空です")

    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError(f"timeout_secondsは正の値を指定してください: {timeout_seconds}")

    # プロンプト構築
    prompt = build_summary_prompt(url, supplementary_urls, hatebu_entry=hatebu_entry)

    # ClaudeAgentOptions作成
    options = ClaudeAgentOptions(
        output_format=OUTPUT_SCHEMA,
        permission_mode="acceptEdits",
        allowed_tools=["WebFetch", "WebSearch"],
        max_turns=10,
    )

    # query実行（タイムアウト付き）
    result_message: ResultMessage | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            async for message in query_func(prompt=prompt, options=options):
                logger.info(f"Received message: {type(message).__name__} - {message}")
                if isinstance(message, ResultMessage):
                    result_message = message
    except MessageParseError as e:
        logger.error("MessageParseError occurred: %s, data=%s", e, e.data)
        raise
    except TimeoutError as e:
        raise QueryTimeoutError(
            f"query処理が{timeout_seconds}秒でタイムアウトしました (URL: {url})"
        ) from e

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

    # detailにはてブコメント全文を結合（結合後のdetail文字列を一度だけ作る）
    detail = parsed.detail
    if hatebu_entry is not None:
        remaining = _DETAIL_TEXT_MAX_CHARS - len(detail)
        hatebu_detail = _build_hatebu_comments_for_detail(hatebu_entry, remaining)
        detail = detail + hatebu_detail

    return EnrichResult(
        blocks=build_unified_blocks(parsed.meta, parsed.summary, detail, hatebu_entry=hatebu_entry),
        fallback_text=build_fallback_text(parsed.meta, parsed.summary, hatebu_entry=hatebu_entry),
    )
