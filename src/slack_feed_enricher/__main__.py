import asyncio
import logging
import signal
from pathlib import Path

from claude_agent_sdk import query
from slack_sdk.web.async_client import AsyncWebClient

from slack_feed_enricher.config import load_config
from slack_feed_enricher.slack import SlackClient
from slack_feed_enricher.worker import run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """アプリケーションのエントリーポイント"""
    # 統合設定を読み込み
    config = load_config(Path("config.yaml"))
    logger.info(
        "Config loaded: polling_interval=%d, message_limit=%d",
        config.polling_interval,
        config.message_limit,
    )

    # Slack クライアントを初期化
    web_client = AsyncWebClient(token=config.slack_bot_token)
    slack_client = SlackClient(web_client)

    # ポーリングループを実行
    await run(
        slack_client=slack_client,
        query_func=query,
        channel_id=config.rss_feed_channel_id,
        message_limit=config.message_limit,
        polling_interval=config.polling_interval,
    )


def setup_signal_handlers(loop: asyncio.AbstractEventLoop, task: asyncio.Task) -> None:
    """シグナルハンドラを設定"""

    def handle_signal(sig: int) -> None:
        logger.info("Received signal %d, shutting down...", sig)
        task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(main())
    setup_signal_handlers(loop, main_task)

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logger.info("Application stopped")
    finally:
        loop.close()
