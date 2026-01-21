import asyncio
from pathlib import Path

from slack_sdk.web.async_client import AsyncWebClient

from slack_feed_enricher.config import load_config
from slack_feed_enricher.slack import SlackClient


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
        limit=config.message_limit,
    )

    print(f"Found {len(messages)} unreplied messages:")
    for msg in messages:
        print(f"  - ts={msg.ts}, reply_count={msg.reply_count}")
        print(f"    text: {msg.text[:100]}..." if len(msg.text) > 100 else f"    text: {msg.text}")


if __name__ == "__main__":
    asyncio.run(main())
