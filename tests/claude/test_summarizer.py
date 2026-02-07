"""summarizer モジュールのテスト"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage

from slack_feed_enricher.claude.exceptions import ClaudeAPIError, StructuredOutputError
from slack_feed_enricher.claude.summarizer import (
    EnrichResult,
    Meta,
    StructuredOutput,
    Summary,
    build_meta_blocks,
    build_summary_blocks,
    build_summary_prompt,
    fetch_and_summarize,
    format_meta_block,
    format_summary_block,
)
from slack_feed_enricher.slack.blocks import SlackSectionBlock, SlackTextObject


class TestStructuredOutputSchema:
    """StructuredOutput Pydanticモデルのスキーマテスト"""

    def test_schema_has_required_top_level_keys(self) -> None:
        """model_json_schema()にmeta, summary, detailがrequiredとして含まれること"""
        schema = StructuredOutput.model_json_schema()
        assert "required" in schema
        assert set(schema["required"]) == {"meta", "summary", "detail"}

    def test_schema_has_properties(self) -> None:
        """model_json_schema()にproperties（meta, summary, detail）が含まれること"""
        schema = StructuredOutput.model_json_schema()
        assert "properties" in schema
        assert "meta" in schema["properties"]
        assert "summary" in schema["properties"]
        assert "detail" in schema["properties"]

    def test_meta_model_fields(self) -> None:
        """Metaモデルに必要なフィールドがすべて定義されていること"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        assert meta.title == "テスト"
        assert meta.url == "https://example.com"
        assert meta.author is None

    def test_summary_model_fields(self) -> None:
        """Summaryモデルにpointsフィールドが定義されていること"""
        summary = Summary(points=["ポイント1", "ポイント2"])
        assert summary.points == ["ポイント1", "ポイント2"]

    def test_structured_output_model_validate(self) -> None:
        """dictからStructuredOutputにmodel_validateできること"""
        data = {
            "meta": {
                "title": "テスト記事",
                "url": "https://example.com",
                "author": "test_author",
                "category_large": "テスト",
                "category_medium": "サブカテゴリ",
                "published_at": "2025-01-15T10:30:00Z",
            },
            "summary": {"points": ["ポイント1"]},
            "detail": "詳細内容",
        }
        result = StructuredOutput.model_validate(data)
        assert result.meta.title == "テスト記事"
        assert result.summary.points == ["ポイント1"]
        assert result.detail == "詳細内容"


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
    async def test_returns_enrich_result_for_single_url(self) -> None:
        """単一URLでEnrichResultが返ること"""
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

        assert isinstance(result, EnrichResult)
        assert result.meta_text == (
            "*テスト記事*\nURL: https://example.com\n著者: test_author\n"
            "カテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z"
        )
        assert result.summary_text == "- ポイント1\n- ポイント2"
        assert result.detail_text == "# 詳細\n記事の詳細内容"
        assert len(result.meta_blocks) == 1
        assert isinstance(result.meta_blocks[0], SlackSectionBlock)
        assert len(result.summary_blocks) == 1
        assert isinstance(result.summary_blocks[0], SlackSectionBlock)

    @pytest.mark.asyncio
    async def test_returns_enrich_result_with_supplementary_urls(self) -> None:
        """補足URL付きでEnrichResultが返ること"""
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

        assert isinstance(result, EnrichResult)
        assert result.meta_text == (
            "*テスト記事*\nURL: https://example.com\n著者: test_author\n"
            "カテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z"
        )
        assert result.summary_text == "- ポイント1"
        assert result.detail_text == "# 詳細\n記事の詳細内容"
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

        with pytest.raises(StructuredOutputError, match="構造化出力のバリデーションに失敗しました"):
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
            "以下のURLをWebFetchで取得し、次の項目を抽出してください。\n"
            "\n"
            "抽出項目:\n"
            "- meta.title: 記事のタイトル\n"
            "- meta.url: 記事のURL\n"
            "- meta.author: 著者名（はてなID、Twitter/X ID、本名など。不明ならnull）\n"
            "- meta.category_large: 大カテゴリー（例: データエンジニアリング。不明ならnull）\n"
            "- meta.category_medium: 中カテゴリー（例: BigQuery。不明ならnull）\n"
            "- meta.published_at: 投稿日時（ISO 8601形式。不明ならnull）\n"
            "- summary.points: 記事の核心を簡潔にまとめた箇条書き（1〜5項目）\n"
            "- detail: 記事内容を構造化した詳細説明（markdown形式）\n"
            "\n"
            "メインURL（記事本体）: https://example.com/article"
        )
        assert prompt == expected

    def test_main_url_with_supplementary_urls(self) -> None:
        """メインURL + 補足URLs → 補足URLセクション付きのプロンプトが生成される"""
        prompt = build_summary_prompt(
            "https://example.com/article",
            supplementary_urls=["https://tool.example.com", "https://ref.example.com"],
        )
        expected = (
            "以下のURLをWebFetchで取得し、次の項目を抽出してください。\n"
            "\n"
            "抽出項目:\n"
            "- meta.title: 記事のタイトル\n"
            "- meta.url: 記事のURL\n"
            "- meta.author: 著者名（はてなID、Twitter/X ID、本名など。不明ならnull）\n"
            "- meta.category_large: 大カテゴリー（例: データエンジニアリング。不明ならnull）\n"
            "- meta.category_medium: 中カテゴリー（例: BigQuery。不明ならnull）\n"
            "- meta.published_at: 投稿日時（ISO 8601形式。不明ならnull）\n"
            "- summary.points: 記事の核心を簡潔にまとめた箇条書き（1〜5項目）\n"
            "- detail: 記事内容を構造化した詳細説明（markdown形式）\n"
            "\n"
            "メインURL（記事本体）: https://example.com/article\n"
            "\n"
            "補足URL:\n"
            "- https://tool.example.com\n"
            "- https://ref.example.com\n"
            "\n"
            "メインURLが主たる情報源です。補足URLは記事内で言及されているツールや"
            "引用元の詳細情報なので、要約に適宜取り込んでください。"
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


class TestBuildMetaBlocks:
    """build_meta_blocks関数のテスト"""

    def test_returns_section_block_with_mrkdwn(self) -> None:
        """MetaモデルからsectionブロックのリストがSlack mrkdwn形式で生成されること"""
        meta = Meta(
            title="BigQueryの最適化テクニック",
            url="https://example.com/article",
            author="yamada_taro",
            category_large="データエンジニアリング",
            category_medium="BigQuery",
            published_at="2025-01-15T10:30:00Z",
        )
        blocks = build_meta_blocks(meta)

        assert len(blocks) == 1
        block = blocks[0]
        assert isinstance(block, SlackSectionBlock)
        assert block.type == "section"
        assert block.text == SlackTextObject(
            type="mrkdwn",
            text=(
                "*BigQueryの最適化テクニック*\n"
                "URL: https://example.com/article\n"
                "著者: yamada_taro\n"
                "カテゴリー: データエンジニアリング / BigQuery\n"
                "投稿日時: 2025-01-15T10:30:00Z"
            ),
        )

    def test_null_fields(self) -> None:
        """nullフィールドのMetaモデルでも正しくブロックが生成されること"""
        meta = Meta(
            title="無名の記事",
            url="https://example.com/anonymous",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        blocks = build_meta_blocks(meta)

        assert len(blocks) == 1
        assert blocks[0].text.text == (
            "*無名の記事*\n"
            "URL: https://example.com/anonymous\n"
            "著者: 不明\n"
            "カテゴリー: 不明\n"
            "投稿日時: 不明"
        )


class TestBuildSummaryBlocks:
    """build_summary_blocks関数のテスト"""

    def test_returns_section_block_with_mrkdwn(self) -> None:
        """SummaryモデルからsectionブロックのリストがSlack mrkdwn形式で生成されること"""
        summary = Summary(points=["ポイント1", "ポイント2", "ポイント3"])
        blocks = build_summary_blocks(summary)

        assert len(blocks) == 1
        block = blocks[0]
        assert isinstance(block, SlackSectionBlock)
        assert block.type == "section"
        assert block.text == SlackTextObject(
            type="mrkdwn",
            text="- ポイント1\n- ポイント2\n- ポイント3",
        )

    def test_single_point(self) -> None:
        """1ポイントのSummaryモデルでも正しくブロックが生成されること"""
        summary = Summary(points=["唯一のポイント"])
        blocks = build_summary_blocks(summary)

        assert len(blocks) == 1
        assert blocks[0].text.text == "- 唯一のポイント"
