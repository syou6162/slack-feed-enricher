"""SlackメッセージからURL抽出を行うモジュール"""

import re

from slack_feed_enricher.slack.client import SlackMessage

# Slack形式: <URL|text> または <URL>
SLACK_URL_PATTERN = re.compile(r"<(https?://[^|>]+)(?:\|[^>]+)?>")
# プレーンURL
PLAIN_URL_PATTERN = re.compile(r"https?://[^\s<>]+")


def extract_urls(message: SlackMessage) -> list[str]:
    """SlackMessageからURLを抽出して返す（重複除去）

    Args:
        message: SlackMessage

    Returns:
        抽出されたURLのリスト（重複なし、出現順）
    """
    urls = []
    seen_urls = set()
    slack_url_positions = set()

    # Slack形式のURL抽出
    for match in SLACK_URL_PATTERN.finditer(message.text):
        url = match.group(1)
        if url not in seen_urls:
            urls.append(url)
            seen_urls.add(url)
        # Slack形式で既に抽出した位置を記録
        slack_url_positions.add((match.start(), match.end()))

    # プレーンURLの抽出（Slack形式と重複しないように）
    for match in PLAIN_URL_PATTERN.finditer(message.text):
        # Slack形式の範囲内にあるURLはスキップ
        is_inside_slack_format = any(start <= match.start() < end for start, end in slack_url_positions)
        if not is_inside_slack_format:
            url = match.group(0)
            if url not in seen_urls:
                urls.append(url)
                seen_urls.add(url)

    return urls
