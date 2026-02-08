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

    parts = code_block_pattern.split(text)
    result: list[str] = []

    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
        else:
            result.append(_escape_non_code_part(part))

    return "".join(result)


def _escape_non_code_part(text: str) -> str:
    """コードブロック外のテキストをエスケープする。

    Slackリンク<url|text>を手動パースし、text部分の>にも対応する。
    リンクの終端は、|の後から最後の>を探すことで特定する。
    """
    result: list[str] = []
    pos = 0

    while pos < len(text):
        # 次の < を探す
        open_pos = text.find("<", pos)
        if open_pos == -1:
            # リンクなし: 残りテキストをエスケープ
            result.append(_escape_text(text[pos:]))
            break

        # < の前のテキストをエスケープ
        result.append(_escape_text(text[pos:open_pos]))

        # | を探す（URLとテキストの区切り）
        pipe_pos = text.find("|", open_pos + 1)
        # > を探す（リンク終端）
        close_pos = text.find(">", open_pos + 1)

        if pipe_pos != -1 and close_pos != -1 and pipe_pos < close_pos:
            # <url|text> 形式: text部分に > や < が含まれうるため、
            # 次のSlackリンク開始パターン(<http, <mailto)より前の最後の > を終端とする
            search_end = len(text)
            search_from = pipe_pos + 1
            while True:
                next_open = text.find("<", search_from)
                if next_open == -1:
                    break
                after = text[next_open + 1:]
                if after.startswith(("http://", "https://", "mailto:")):
                    search_end = next_open
                    break
                search_from = next_open + 1
            final_close = text.rfind(">", pipe_pos + 1, search_end)
            if final_close >= 0:
                url = text[open_pos + 1:pipe_pos]
                link_text = text[pipe_pos + 1:final_close]
                result.append(f"<{url}|{_escape_text(link_text)}>")
                pos = final_close + 1
            else:
                # > が見つからない: < をエスケープして進む
                result.append(_escape_text("<"))
                pos = open_pos + 1
        elif close_pos != -1:
            inner = text[open_pos + 1:close_pos]
            if inner.startswith(("http://", "https://", "mailto:")):
                # <url> 形式（パイプなし）: そのまま保持
                result.append(text[open_pos:close_pos + 1])
                pos = close_pos + 1
            else:
                # URLでない: < をエスケープして進む
                result.append(_escape_text("<"))
                pos = open_pos + 1
        else:
            # 閉じ > なし: < をエスケープして進む
            result.append(_escape_text("<"))
            pos = open_pos + 1

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
