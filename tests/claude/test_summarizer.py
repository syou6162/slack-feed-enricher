"""summarizer モジュールのテスト"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ResultMessage

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

        assert isinstance(result, list)
        assert len(result) == 3
        # メタ情報ブロック
        assert "テスト記事" in result[0]
        assert "https://example.com" in result[0]
        # 要約ブロック
        assert "ポイント1" in result[1]
        assert "ポイント2" in result[1]
        # 詳細ブロック
        assert result[2] == "# 詳細\n記事の詳細内容"

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

        assert isinstance(result, list)
        assert len(result) == 3
        # プロンプトに補足URLが含まれていること
        assert len(received_prompts) == 1
        assert "https://tool.example.com" in received_prompts[0]
        assert "https://ref.example.com" in received_prompts[0]
        assert "補足URL" in received_prompts[0]

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
        """structured_outputがNoneの場合にStructuredOutputErrorが発生すること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = None

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        with pytest.raises(StructuredOutputError, match="構造化出力が取得できませんでした"):
            await fetch_and_summarize(mock_query, "https://example.com")


class TestBuildSummaryPrompt:
    """build_summary_prompt関数のテスト"""

    def test_main_url_only(self) -> None:
        """メインURLのみ → プロンプトにURLが含まれる"""
        prompt = build_summary_prompt("https://example.com/article")
        assert "https://example.com/article" in prompt
        # 補足URLセクションが含まれないこと
        assert "補足URL" not in prompt

    def test_main_url_with_supplementary_urls(self) -> None:
        """メインURL + 補足URLs → プロンプトに全URLが含まれる"""
        prompt = build_summary_prompt(
            "https://example.com/article",
            supplementary_urls=["https://tool.example.com", "https://ref.example.com"],
        )
        assert "https://example.com/article" in prompt
        assert "https://tool.example.com" in prompt
        assert "https://ref.example.com" in prompt
        # 補足URLセクションが含まれること
        assert "補足URL" in prompt

    def test_supplementary_urls_empty_list(self) -> None:
        """補足URLが空リスト → メインURLのみの場合と同様に動作"""
        prompt = build_summary_prompt("https://example.com/article", supplementary_urls=[])
        assert "https://example.com/article" in prompt
        assert "補足URL" not in prompt

    def test_supplementary_urls_none(self) -> None:
        """supplementary_urls=None（デフォルト値） → メインURLのみの場合と同様に動作"""
        prompt = build_summary_prompt("https://example.com/article", supplementary_urls=None)
        assert "https://example.com/article" in prompt
        assert "補足URL" not in prompt


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
        assert "BigQueryの最適化テクニック" in result
        assert "https://example.com/article" in result
        assert "yamada_taro" in result
        assert "データエンジニアリング" in result
        assert "BigQuery" in result
        assert "2025-01-15T10:30:00Z" in result

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
        assert "無名の記事" in result
        assert "https://example.com/anonymous" in result
        assert "不明" in result


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
        assert "BigQueryのパーティショニングの活用方法" in result
        assert "クエリコストの削減テクニック" in result
        assert "マテリアライズドビューの効果的な使い方" in result
        # 箇条書き形式であること
        assert result.count("- ") >= 3

    def test_single_point(self) -> None:
        """1ポイントのみの場合"""
        summary = {"points": ["唯一のポイント"]}
        result = format_summary_block(summary)
        assert "唯一のポイント" in result
        assert "- " in result
