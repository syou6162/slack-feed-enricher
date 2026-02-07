"""summarizer モジュールのテスト"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ResultMessage

from slack_feed_enricher.claude.exceptions import ClaudeAPIError, StructuredOutputError
from slack_feed_enricher.claude.summarizer import build_summary_prompt, fetch_and_summarize


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
    async def test_returns_markdown_for_single_url(self) -> None:
        """単一URLで要約markdownが返ること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {"markdown": "# タイトル\n- ポイント1"}

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        result = await fetch_and_summarize(mock_query, "https://example.com")

        assert result == "# タイトル\n- ポイント1"

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
