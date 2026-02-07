"""Markdown→Slack mrkdwn変換モジュール

GitHub MarkdownをSlack mrkdwn記法に変換する薄いラッパー。
ライブラリ差し替え時の変更箇所を限定するため、変換ロジックを集約する。
"""

import re

from markdown_to_mrkdwn import SlackMarkdownConverter


def _escape_slack_special_chars(text: str) -> str:
    """Slackリンク記法を保護しつつ、特殊文字をエスケープする。

    - `<url|text>` のURL部分はそのまま保持
    - `<url|text>` のテキスト部分の &, <, > をエスケープ
    - リンク外テキストの &, <, > をエスケープ
    - コードブロック(```)およびインラインコード(`)内はエスケープしない
    """
    code_block_pattern = re.compile(r"(```[\s\S]*?```|`[^`]+`)")
    slack_link_pattern = re.compile(r"<([^|>]+)\|([^>]+)>")

    parts = code_block_pattern.split(text)
    result: list[str] = []

    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
        else:
            result.append(_escape_non_code_part(part, slack_link_pattern))

    return "".join(result)


def _escape_non_code_part(text: str, slack_link_pattern: re.Pattern[str]) -> str:
    """コードブロック外のテキストをエスケープする。

    re.splitでキャプチャグループを使うと、セグメントは
    [text, url, link_text, text, url, link_text, ..., text] の形になる。
    3個ずつ（通常テキスト, URL, リンクテキスト）を処理する。
    """
    segments = slack_link_pattern.split(text)
    result: list[str] = []

    i = 0
    while i < len(segments):
        result.append(_escape_text(segments[i]))
        if i + 2 < len(segments):
            url = segments[i + 1]
            link_text = segments[i + 2]
            result.append(f"<{url}|{_escape_text(link_text)}>")
        i += 3

    return "".join(result)


def _escape_text(text: str) -> str:
    """テキスト内の &, <, > をエスケープする。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def convert_markdown_to_mrkdwn(text: str) -> str:
    """MarkdownテキストをSlack mrkdwn記法に変換する。

    Args:
        text: Markdown形式のテキスト

    Returns:
        Slack mrkdwn形式に変換されたテキスト
    """
    converter = SlackMarkdownConverter()
    converted = converter.convert(text)
    return _escape_slack_special_chars(converted)
