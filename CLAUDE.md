# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 開発コマンド

```bash
# 依存関係のインストール
uv sync

# すべてのテストを実行
uv run pytest

# 特定のテストファイルを実行
uv run pytest tests/test_worker.py

# Lintチェック
uv run ruff check src/ tests/

# 型チェック
uv run ty check src/

# pre-commitフック（すべてのチェックを実行）
uv run pre-commit run --all-files
```

## アーキテクチャ概要

### システム全体の流れ

```
main() → run() (ポーリングループ)
  ↓
fetch_unreplied_messages() (Slack API: チャンネル履歴取得 + スレッド返信確認)
  ↓
extract_url() (メッセージからURLを抽出)
  ↓
fetch_and_summarize() (Claude Agent SDK: WebFetch + 構造化出力)
  ↓
post_thread_reply() (Slack API: スレッド返信投稿)
```

### 設計の重要ポイント

1. **ポーリング方式**: Socket Modeを使わず、10分間隔でポーリング
   - `worker.py`の`run()`が無限ループで定期実行
   - タイムアウト機構あり（`polling_interval`超過時に早期return）

2. **返信済み判定**: Slack APIの`conversations.replies`で判定
   - スレッド返信があるメッセージはスキップ
   - 新規メッセージのみ処理対象

3. **構造化出力**: Claude Agent SDKの`output_format`で`{"markdown": string}`スキーマを使用
   - WebFetch/WebSearchツールを許可
   - `ClaudeSDKClient`をコンテキストマネージャーとして使用

4. **設定管理**: 環境変数（`.env`）とYAML（`config.yaml`）を統合
   - `config/env.py`: 環境変数（`SLACK_BOT_TOKEN`, `RSS_FEED_CHANNEL_ID`）
   - `config/app.py`: YAML設定（`polling_interval`, `message_limit`）
   - `config/config.py`: 統合Config

### モジュール間の依存関係

```
__main__.py
  ├─ config/ (設定読み込み)
  ├─ slack/client.py (SlackClient初期化)
  └─ worker.py (ポーリングループ)
       ├─ slack/client.py (未返信メッセージ取得、スレッド投稿)
       ├─ slack/url_extractor.py (URL抽出)
       └─ claude/summarizer.py (要約生成)
```

## 開発時の注意点

### t_wada式TDD
- Red-Green-Refactorサイクルを厳守
- 小さなステップで進める（一度に一つのことだけ）

### Linter設定
- ruffを使用（ignoreは基本禁止）
- tests/配下はARGルールを無効化

### 型チェック
- tyを使用してsrc/配下をチェック
