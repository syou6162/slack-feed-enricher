"""SlackメッセージからURL抽出を行うモジュール"""

import re

from slack_feed_enricher.slack.client import SlackMessage

# Slack形式: <URL|text> または <URL>
SLACK_URL_PATTERN = re.compile(r"<(https?://[^|>]+)(?:\|[^>]+)?>")
# プレーンURL
PLAIN_URL_PATTERN = re.compile(r"https?://[^\s<>]+")


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
