# slack-feed-enricher 開発者ガイド

このドキュメントはslack-feed-enricherプロジェクトの開発者向けガイドです。

## プロジェクト構成

```
src/slack_feed_enricher/
├── __main__.py           # エントリーポイント
├── worker.py             # ポーリングワーカー
├── config/               # 設定管理
│   ├── env.py           # 環境変数設定（EnvConfig）
│   ├── app.py           # YAML設定（AppConfig）
│   └── config.py        # 統合設定（Config）
├── slack/                # Slack SDK連携
│   ├── client.py        # SlackClient
│   ├── url_extractor.py # URL抽出機能
│   └── exceptions.py    # Slack関連例外
└── claude/               # Claude Agent SDK連携
    ├── summarizer.py    # URL要約機能
    └── exceptions.py    # Claude関連例外
```

## 各モジュールの役割

### __main__.py
アプリケーションのエントリーポイント。設定を読み込み、Slack AsyncWebClientを初期化してポーリングループを開始します。シグナルハンドラ（SIGINT, SIGTERM）でgraceful shutdownを実現しています。

### worker.py
ポーリングワーカーの実装。以下の機能を提供します:

- `EnrichAndReplyResult`: 処理結果を保持するデータクラス
- `send_enriched_messages()`: 要約をSlackスレッドに投稿
- `enrich_and_reply_pending_messages()`: 未返信メッセージをエンリッチして返信
- `run()`: ポーリングループ（タイムアウト機構付き）

### config/
設定管理モジュール。環境変数とYAML設定を統合して管理します:

- `EnvConfig`: 環境変数（`SLACK_BOT_TOKEN`, `RSS_FEED_CHANNEL_ID`）
- `AppConfig`: YAML設定（`polling_interval`, `message_limit`）
- `Config`: 上記2つを統合した設定クラス

### slack/
Slack SDK連携モジュール:

- `SlackClient`: Slack API操作を提供
  - `fetch_channel_history()`: チャンネル履歴取得
  - `has_thread_replies()`: スレッド返信有無確認
  - `fetch_unreplied_messages()`: 未返信メッセージ取得
  - `post_thread_reply()`: スレッド返信投稿
- `url_extractor.py`: SlackメッセージからURL抽出（`<URL|text>`形式とプレーンURL対応）
- `SlackMessage`: メッセージデータクラス（ts, text, reply_count）

### claude/
Claude Agent SDK連携モジュール:

- `fetch_and_summarize()`: URLをWebFetchで取得しmarkdown形式で要約
  - 構造化出力スキーマ使用: `{"markdown": string}`
  - ClaudeAgentOptions: WebFetch, WebSearchツール許可
- 例外定義: `ClaudeSDKError`, `NoResultMessageError`, `ClaudeAPIError`, `StructuredOutputError`

## 開発時の注意点

### t_wada式TDD
このプロジェクトではt_wada式のTDD（テスト駆動開発）を実践しています:

1. **TODOリスト**: 実装前に何をテストするかのTODOリストを作成し、小さなステップに分解
2. **Red-Green-Refactorサイクル**:
   - Red: 失敗するテストを先に書く
   - Green: テストが通る最小限のコードを書く
   - Refactor: コードを改善する
3. **原則**:
   - テストコードとプロダクションコードを交互に書く
   - 一度に一つのことだけに集中する
   - 小さく確実なステップで進める

### Linter設定
ruffを使用（基本的にignoreは禁止）:

- **有効ルール**: I (isort), UP (pyupgrade), F (pyflakes), RET (return), SIM (simplify), B (bugbear), N (pep8-naming), DTZ (datetime), ARG (unused-args), PL (Pylint), W/E (pycodestyle), ANN (type annotations), TID251 (banned imports)
- **無効ルール**: PLR2004, PLR0911, PLR0912, PLR0913, SIM108
- **tests/**ではARGルールを無効化

### 型チェック
tyを使用してsrc/配下の型チェックを実施します。

### コミット
小まめにコミットすることを推奨します（semantic-committing）。

## 開発環境のセットアップ

```bash
# 依存関係のインストール
uv sync

# pre-commitフックのインストール
uv run pre-commit install
```

## テストの実行

```bash
# すべてのテストを実行
uv run pytest

# 特定のテストファイルを実行
uv run pytest tests/test_worker.py

# カバレッジ付きで実行
uv run pytest --cov=src/slack_feed_enricher
```

## Linter/型チェックの実行

```bash
# Ruff lintチェック
uv run ruff check src/ tests/

# Ruff自動修正
uv run ruff check --fix src/ tests/

# ty型チェック
uv run ty check src/

# pre-commitフックをすべて実行
uv run pre-commit run --all-files
```

## CI/CD

GitHub Actionsで以下のチェックを実行しています:

- **test.yml**: pytestでテスト実行
- **ruff.yml**: Ruff lintチェック
- **ty.yml**: ty型チェック（src/配下）

## 依存関係

主要な依存パッケージ:

- `slack-sdk`: Slack API連携
- `claude-agent-sdk`: Claude API連携
- `pydantic`: 設定バリデーション
- `pyyaml`: YAML設定ファイル読み込み
- `aiohttp`: 非同期HTTP通信
- `pytest`, `pytest-asyncio`: テストフレームワーク
- `ruff`: Linter
- `ty`: 型チェッカー

## アーキテクチャの特徴

### ポーリング方式
Socket Modeは使わず、main関数が常駐してポーリングする方式を採用しています。

### 返信済み判定
返信済みかどうかはSlack APIでスレッド返信の有無を確認して判定します。

### タイムアウト機構
`enrich_and_reply_pending_messages()`にタイムアウト機構を実装し、`polling_interval`超過時に早期returnして次のポーリングサイクルに移行します。

### 構造化出力
Claude Agent SDKの構造化出力機能を使用して、markdownフィールドのみを持つJSONスキーマで応答を取得します。

## トラブルシューティング

### テストが失敗する
```bash
# キャッシュをクリア
uv run pytest --cache-clear
```

### pre-commitフックが失敗する
```bash
# すべてのフックを再実行
uv run pre-commit run --all-files
```

### 型チェックエラー
```bash
# src/配下のみチェック
uv run ty check src/
```
