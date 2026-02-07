"""SlackメッセージからURL抽出を行うモジュール"""

import re
from dataclasses import dataclass, field

from slack_feed_enricher.slack.client import SlackMessage

# Slack形式: <URL|text> または <URL>
SLACK_URL_PATTERN = re.compile(r"<(https?://[^|>]+)(?:\|[^>]+)?>")
# プレーンURL
PLAIN_URL_PATTERN = re.compile(r"https?://[^\s<>]+")


@dataclass
class ExtractedUrls:
    """URL抽出結果を格納するデータクラス"""

    main_url: str | None = None
    supplementary_urls: list[str] = field(default_factory=list)


def extract_urls(message: SlackMessage) -> ExtractedUrls:
    """SlackMessageから全URLを出現順に抽出して返す

    テキストを先頭から走査し、Slack形式URL（<url|text>や<url>）と
    プレーンURLの両方を出現順に統合して抽出する。
    重複URLは後出のものを除外する。

    Args:
        message: SlackMessage

    Returns:
        ExtractedUrls（1つ目がmain_url、2つ目以降がsupplementary_urls）
    """
    text = message.text
    if not text:
        return ExtractedUrls()

    # Slack形式とプレーンURLの両方のマッチを出現位置順に統合
    matches: list[tuple[int, str]] = []

    # Slack形式URLの位置を記録（プレーンURL検出時に除外するため）
    slack_ranges: list[tuple[int, int]] = []
    for match in SLACK_URL_PATTERN.finditer(text):
        matches.append((match.start(), match.group(1)))
        slack_ranges.append((match.start(), match.end()))

    # プレーンURLを検出（Slack形式URLの範囲内にあるものは除外）
    for match in PLAIN_URL_PATTERN.finditer(text):
        pos = match.start()
        in_slack_range = any(start <= pos < end for start, end in slack_ranges)
        if not in_slack_range:
            matches.append((pos, match.group(0)))

    # 出現位置順にソート
    matches.sort(key=lambda x: x[0])

    # 重複排除（出現順を維持）
    seen: set[str] = set()
    urls: list[str] = []
    for _, url in matches:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    if not urls:
        return ExtractedUrls()

    return ExtractedUrls(main_url=urls[0], supplementary_urls=urls[1:])


def extract_url(message: SlackMessage) -> str | None:
    """SlackMessageから先頭のURLを抽出して返す

    Args:
        message: SlackMessage

    Returns:
        抽出されたURL（URLがない場合はNone）
    """
    # Slack形式のURL抽出
    for match in SLACK_URL_PATTERN.finditer(message.text):
        return match.group(1)

    # プレーンURLの抽出（Slack形式と重複しないように）
    for match in PLAIN_URL_PATTERN.finditer(message.text):
        return match.group(0)

    return None
