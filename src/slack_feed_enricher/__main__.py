from pathlib import Path

from dotenv import load_dotenv

from slack_feed_enricher.config import load_config


def main() -> str:
    """アプリケーションのエントリーポイント"""
    # .envファイルを読み込み
    load_dotenv()

    # 統合設定を読み込み
    config = load_config(Path("config.yaml"))

    return f"Config loaded successfully: polling_interval={config.polling_interval}, message_limit={config.message_limit}"


if __name__ == "__main__":
    print(main())
