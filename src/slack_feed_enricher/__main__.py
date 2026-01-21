import asyncio
import logging
from pathlib import Path

from claude_agent_sdk import query
from slack_sdk.web.async_client import AsyncWebClient

from slack_feed_enricher.claude import fetch_and_summarize
from slack_feed_enricher.config import load_config
from slack_feed_enricher.slack import SlackClient, extract_urls

logging.basicConfig(level=logging.INFO)

# 動作確認用にメッセージ数を制限
TEST_MESSAGE_LIMIT = 3


async def main() -> None:
    """アプリケーションのエントリーポイント"""
    # 統合設定を読み込み
    config = load_config(Path("config.yaml"))
    print(f"Config loaded: polling_interval={config.polling_interval}, message_limit={config.message_limit}")

    # Slack クライアントを初期化
    web_client = AsyncWebClient(token=config.slack_bot_token)
    slack_client = SlackClient(web_client)

    # 未返信メッセージを取得
    print(f"\nFetching unreplied messages from channel {config.rss_feed_channel_id}...")
    messages = await slack_client.fetch_unreplied_messages(
        config.rss_feed_channel_id,
        limit=TEST_MESSAGE_LIMIT,  # 動作確認用に制限
    )

    print(f"Found {len(messages)} unreplied messages:")
    for msg in messages:
        print(f"  - ts={msg.ts}, reply_count={msg.reply_count}")
        print(f"    text: {msg.text[:100]}..." if len(msg.text) > 100 else f"    text: {msg.text}")

        # URL抽出
        urls = extract_urls(msg)
        if urls:
            print(f"    URLs: {urls}")

            # Claude Agent SDKで要約取得
            try:
                result = await fetch_and_summarize(query, urls)
                print(f"    Summary (JSON): {result}")
            except Exception as e:
                print(f"    Summary error: {e}")
        else:
            print("    URLs: (none)")


if __name__ == "__main__":
    asyncio.run(main())
