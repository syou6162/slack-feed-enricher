# slack-feed-enricher

SlackのRSSフィードチャンネルに投稿されたURLを自動的に要約してスレッド返信するツールです。

## 機能

- 指定したSlackチャンネルを定期的に監視（デフォルト: 10分間隔）
- スレッド返信がないメッセージからURLを抽出
- Claude Agent SDKを使ってURLの内容を取得・要約
- 要約をmarkdown形式でスレッドに自動返信

## 必要なもの

- Python 3.14以上
- [uv](https://docs.astral.sh/uv/)（パッケージマネージャー）
- Slackワークスペースとアプリ

## Slackアプリのセットアップ

### 1. Slackアプリの作成

[Slack API](https://api.slack.com/apps)でアプリを作成します。

### 2. 必要なスコープを追加

**OAuth & Permissions** から以下のBot Token Scopesを追加してください:

- `channels:history` - チャンネル履歴の取得
- `chat:write` - スレッド返信の投稿

### 3. Bot User OAuth Tokenの取得

**OAuth & Permissions** ページから **Bot User OAuth Token**（`xoxb-`で始まるトークン）をコピーしてください。

### 4. アプリをワークスペースにインストール

**Install App** からワークスペースにインストールします。

### 5. チャンネルにアプリを追加

監視したいチャンネルにアプリを追加してください:

```
/invite @your-app-name
```

## インストール

```bash
git clone https://github.com/syou6162/slack-feed-enricher.git
cd slack-feed-enricher
uv sync
```

## 設定

### 環境変数

`.env`ファイルを作成し、以下の環境変数を設定してください:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
RSS_FEED_CHANNEL_ID=C0123456789
```

- `SLACK_BOT_TOKEN`: Slackアプリの Bot User OAuth Token
- `RSS_FEED_CHANNEL_ID`: 監視対象のチャンネルID

チャンネルIDの確認方法: Slackアプリでチャンネルを右クリック → 「チャンネル詳細を表示」→ 一番下の「チャンネルID」

### 設定ファイル（オプション）

`config.yaml`で動作をカスタマイズできます:

```yaml
polling_interval: 600   # ポーリング間隔（秒）、デフォルト: 600（10分）
message_limit: 200      # 1回あたりの取得メッセージ数、デフォルト: 200
```

## 実行

```bash
uv run slack-feed-enricher
```

### 停止方法

`Ctrl+C`で停止できます（graceful shutdown対応）。

## ライセンス

MIT License - 詳細は[LICENSE](LICENSE)ファイルを参照してください。

## 作者

Yasuhisa Yoshida
