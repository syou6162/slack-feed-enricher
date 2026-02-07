"""summarizer モジュールのテスト"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from slack_feed_enricher.claude.exceptions import ClaudeAPIError, StructuredOutputError
from slack_feed_enricher.claude.summarizer import (
    build_summary_prompt,
    fetch_and_summarize,
    format_meta_block,
    format_summary_block,
)


class TestFetchAndSummarize:
    """fetch_and_summarize関数のテスト"""

    @pytest.mark.asyncio
    async def test_raises_value_error_for_empty_url(self) -> None:
        """空のURLでValueErrorが発生すること"""

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield None

        with pytest.raises(ValueError, match="URLが空です"):
            await fetch_and_summarize(mock_query, "")

    @pytest.mark.asyncio
    async def test_returns_three_blocks_for_single_url(self) -> None:
        """単一URLで3ブロックのリストが返ること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {
            "meta": {
                "title": "テスト記事",
                "url": "https://example.com",
                "author": "test_author",
                "category_large": "テスト",
                "category_medium": "サブカテゴリ",
                "published_at": "2025-01-15T10:30:00Z",
            },
            "summary": {"points": ["ポイント1", "ポイント2"]},
            "detail": "# 詳細\n記事の詳細内容",
        }

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        result = await fetch_and_summarize(mock_query, "https://example.com")

        assert result == [
            "*テスト記事*\nURL: https://example.com\n著者: test_author\nカテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z",
            "- ポイント1\n- ポイント2",
            "# 詳細\n記事の詳細内容",
        ]

    @pytest.mark.asyncio
    async def test_returns_three_blocks_with_supplementary_urls(self) -> None:
        """補足URL付きで3ブロックのリストが返ること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {
            "meta": {
                "title": "テスト記事",
                "url": "https://example.com",
                "author": "test_author",
                "category_large": "テスト",
                "category_medium": "サブカテゴリ",
                "published_at": "2025-01-15T10:30:00Z",
            },
            "summary": {"points": ["ポイント1"]},
            "detail": "# 詳細\n記事の詳細内容",
        }

        received_prompts: list[str] = []

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:
            """モックquery関数（プロンプトを記録）"""
            received_prompts.append(str(kwargs.get("prompt", "")))
            yield mock_result

        result = await fetch_and_summarize(
            mock_query,
            "https://example.com",
            supplementary_urls=["https://tool.example.com", "https://ref.example.com"],
        )

        assert result == [
            "*テスト記事*\nURL: https://example.com\n著者: test_author\nカテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z",
            "- ポイント1",
            "# 詳細\n記事の詳細内容",
        ]
        # プロンプトが補足URL付きで構築されていること
        assert len(received_prompts) == 1
        expected_prompt = build_summary_prompt(
            "https://example.com",
            supplementary_urls=["https://tool.example.com", "https://ref.example.com"],
        )
        assert received_prompts[0] == expected_prompt

    @pytest.mark.asyncio
    async def test_passes_max_turns_in_options(self) -> None:
        """ClaudeAgentOptionsにmax_turnsが設定されていること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {
            "meta": {
                "title": "テスト",
                "url": "https://example.com",
                "author": None,
                "category_large": None,
                "category_medium": None,
                "published_at": None,
            },
            "summary": {"points": ["ポイント"]},
            "detail": "詳細",
        }

        received_options: list[ClaudeAgentOptions] = []

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:
            """モックquery関数（optionsを記録）"""
            options = kwargs.get("options")
            if isinstance(options, ClaudeAgentOptions):
                received_options.append(options)
            yield mock_result

        await fetch_and_summarize(mock_query, "https://example.com")

        assert len(received_options) == 1
        assert received_options[0].max_turns == 10

    @pytest.mark.asyncio
    async def test_raises_structured_output_error_when_keys_missing(self) -> None:
        """structured_outputに必要なキーが欠損している場合にStructuredOutputErrorが発生すること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {"meta": {"title": "テスト"}}

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        with pytest.raises(StructuredOutputError, match="構造化出力に必要なキーが欠損しています"):
            await fetch_and_summarize(mock_query, "https://example.com")

    @pytest.mark.asyncio
    async def test_raises_claude_api_error_on_sdk_error(self) -> None:
        """SDKエラー時にClaudeAPIErrorが発生すること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = True
        mock_result.result = "API error"

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        with pytest.raises(ClaudeAPIError, match="要約処理でエラーが発生しました") as exc_info:
            await fetch_and_summarize(mock_query, "https://example.com")

        assert exc_info.value.result == "API error"

    @pytest.mark.asyncio
    async def test_raises_structured_output_error_when_structured_output_is_none(self) -> None:
        """structured_outputがNoneの場合にStructuredOutputErrorが発生し、subtypeとresultが含まれること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = None
        mock_result.subtype = "error_max_structured_output_retries"
        mock_result.result = "Failed to generate structured output"

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        with pytest.raises(StructuredOutputError) as exc_info:
            await fetch_and_summarize(mock_query, "https://example.com")

        assert str(exc_info.value) == (
            "構造化出力が取得できませんでした"
            " (subtype=error_max_structured_output_retries, result=Failed to generate structured output)"
        )


class TestBuildSummaryPrompt:
    """build_summary_prompt関数のテスト"""

    def test_main_url_only(self) -> None:
        """メインURLのみ → 補足URLセクションなしのプロンプトが生成される"""
        prompt = build_summary_prompt("https://example.com/article")
        expected = (
            "以下のURLの内容をすべてWebFetchで取得してください。\n"
            "\n"
            "メインURL（記事本体）: https://example.com/article\n"
            "\n"
            "取得した内容をもとに、以下のJSON形式で出力してください：\n"
            "\n"
            "{\n"
            '  "meta": {\n'
            '    "title": "記事のタイトル",\n'
            '    "url": "記事のURL",\n'
            '    "author": "著者名（はてなID、Twitter/X ID、本名など。取得できない場合はnull）",\n'
            '    "category_large": "大カテゴリー（例: データエンジニアリング。判定できない場合はnull）",\n'
            '    "category_medium": "中カテゴリー（例: BigQuery。判定できない場合はnull）",\n'
            '    "published_at": "投稿日時（ISO 8601形式。取得できない場合はnull）"\n'
            "  },\n"
            '  "summary": {\n'
            '    "points": ["箇条書きポイント1", "ポイント2", ...]  // 記事の核心を簡潔にまとめる。最大5項目\n'
            "  },\n"
            '  "detail": "記事内容を構造化した詳細説明（markdown形式）"\n'
            "}\n"
            "\n"
            "注意事項:\n"
            "- detailは要約ではなく、記事の内容を網羅的に記述してください\n"
            "- ただし、Slack APIのメッセージ長制限（40,000文字）を考慮し、適度な長さに収めてください"
        )
        assert prompt == expected

    def test_main_url_with_supplementary_urls(self) -> None:
        """メインURL + 補足URLs → 補足URLセクション付きのプロンプトが生成される"""
        prompt = build_summary_prompt(
            "https://example.com/article",
            supplementary_urls=["https://tool.example.com", "https://ref.example.com"],
        )
        expected = (
            "以下のURLの内容をすべてWebFetchで取得してください。\n"
            "\n"
            "メインURL（記事本体）: https://example.com/article\n"
            "\n"
            "補足URL:\n"
            "- https://tool.example.com\n"
            "- https://ref.example.com\n"
            "\n"
            "メインURLが主たる情報源です。補足URLは記事内で言及されているツールや"
            "引用元の詳細情報なので、要約に適宜取り込んでください。\n"
            "\n"
            "取得した内容をもとに、以下のJSON形式で出力してください：\n"
            "\n"
            "{\n"
            '  "meta": {\n'
            '    "title": "記事のタイトル",\n'
            '    "url": "記事のURL",\n'
            '    "author": "著者名（はてなID、Twitter/X ID、本名など。取得できない場合はnull）",\n'
            '    "category_large": "大カテゴリー（例: データエンジニアリング。判定できない場合はnull）",\n'
            '    "category_medium": "中カテゴリー（例: BigQuery。判定できない場合はnull）",\n'
            '    "published_at": "投稿日時（ISO 8601形式。取得できない場合はnull）"\n'
            "  },\n"
            '  "summary": {\n'
            '    "points": ["箇条書きポイント1", "ポイント2", ...]  // 記事の核心を簡潔にまとめる。最大5項目\n'
            "  },\n"
            '  "detail": "記事内容を構造化した詳細説明（markdown形式）"\n'
            "}\n"
            "\n"
            "注意事項:\n"
            "- detailは要約ではなく、記事の内容を網羅的に記述してください\n"
            "- ただし、Slack APIのメッセージ長制限（40,000文字）を考慮し、適度な長さに収めてください"
        )
        assert prompt == expected

    def test_supplementary_urls_empty_list(self) -> None:
        """補足URLが空リスト → メインURLのみの場合と同一の出力"""
        prompt_empty = build_summary_prompt("https://example.com/article", supplementary_urls=[])
        prompt_none = build_summary_prompt("https://example.com/article")
        assert prompt_empty == prompt_none

    def test_supplementary_urls_none(self) -> None:
        """supplementary_urls=None（デフォルト値） → メインURLのみの場合と同一の出力"""
        prompt_explicit_none = build_summary_prompt("https://example.com/article", supplementary_urls=None)
        prompt_default = build_summary_prompt("https://example.com/article")
        assert prompt_explicit_none == prompt_default


class TestFormatMetaBlock:
    """format_meta_block関数のテスト"""

    def test_all_fields_present(self) -> None:
        """全フィールドが埋まっている場合の出力"""
        meta = {
            "title": "BigQueryの最適化テクニック",
            "url": "https://example.com/article",
            "author": "yamada_taro",
            "category_large": "データエンジニアリング",
            "category_medium": "BigQuery",
            "published_at": "2025-01-15T10:30:00Z",
        }
        result = format_meta_block(meta)
        assert result == (
            "*BigQueryの最適化テクニック*\n"
            "URL: https://example.com/article\n"
            "著者: yamada_taro\n"
            "カテゴリー: データエンジニアリング / BigQuery\n"
            "投稿日時: 2025-01-15T10:30:00Z"
        )

    def test_category_medium_only(self) -> None:
        """category_largeがnullでcategory_mediumのみの場合、mediumのみ表示"""
        meta = {
            "title": "BigQuery入門",
            "url": "https://example.com/bq",
            "author": "taro",
            "category_large": None,
            "category_medium": "BigQuery",
            "published_at": "2025-01-15T10:30:00Z",
        }
        result = format_meta_block(meta)
        assert result == (
            "*BigQuery入門*\n"
            "URL: https://example.com/bq\n"
            "著者: taro\n"
            "カテゴリー: BigQuery\n"
            "投稿日時: 2025-01-15T10:30:00Z"
        )

    def test_category_large_only(self) -> None:
        """category_mediumがnullでcategory_largeのみの場合、largeのみ表示"""
        meta = {
            "title": "データ基盤の話",
            "url": "https://example.com/data",
            "author": "taro",
            "category_large": "データエンジニアリング",
            "category_medium": None,
            "published_at": "2025-01-15T10:30:00Z",
        }
        result = format_meta_block(meta)
        assert result == (
            "*データ基盤の話*\n"
            "URL: https://example.com/data\n"
            "著者: taro\n"
            "カテゴリー: データエンジニアリング\n"
            "投稿日時: 2025-01-15T10:30:00Z"
        )

    def test_null_fields(self) -> None:
        """nullフィールドの扱い（著者不明、カテゴリー不明、投稿日時不明）"""
        meta = {
            "title": "無名の記事",
            "url": "https://example.com/anonymous",
            "author": None,
            "category_large": None,
            "category_medium": None,
            "published_at": None,
        }
        result = format_meta_block(meta)
        assert result == (
            "*無名の記事*\n"
            "URL: https://example.com/anonymous\n"
            "著者: 不明\n"
            "カテゴリー: 不明\n"
            "投稿日時: 不明"
        )


class TestFormatSummaryBlock:
    """format_summary_block関数のテスト"""

    def test_multiple_points(self) -> None:
        """複数ポイントの箇条書き出力"""
        summary = {
            "points": [
                "BigQueryのパーティショニングの活用方法",
                "クエリコストの削減テクニック",
                "マテリアライズドビューの効果的な使い方",
            ]
        }
        result = format_summary_block(summary)
        assert result == (
            "- BigQueryのパーティショニングの活用方法\n"
            "- クエリコストの削減テクニック\n"
            "- マテリアライズドビューの効果的な使い方"
        )

    def test_single_point(self) -> None:
        """1ポイントのみの場合"""
        summary = {"points": ["唯一のポイント"]}
        result = format_summary_block(summary)
        assert result == "- 唯一のポイント"
