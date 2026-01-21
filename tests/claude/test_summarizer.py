"""summarizer モジュールのテスト"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import ResultMessage

from slack_feed_enricher.claude.summarizer import fetch_and_summarize


class TestFetchAndSummarize:
    """fetch_and_summarize関数のテスト"""

    @pytest.mark.asyncio
    async def test_raises_value_error_for_empty_urls(self) -> None:
        """空のURLリストでValueErrorが発生すること"""

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield None

        mock_options = None

        with pytest.raises(ValueError, match="URLリストが空です"):
            await fetch_and_summarize(mock_query, mock_options, [])

    @pytest.mark.asyncio
    async def test_returns_markdown_for_single_url(self) -> None:
        """単一URLで要約markdownが返ること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {"markdown": "# タイトル\n- ポイント1"}

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        mock_options = None

        result = await fetch_and_summarize(mock_query, mock_options, ["https://example.com"])

        assert result == "# タイトル\n- ポイント1"

    @pytest.mark.asyncio
    async def test_returns_markdown_for_multiple_urls(self) -> None:
        """複数URLで要約markdownが返ること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {"markdown": "# 要約\n- URL1の内容\n- URL2の内容"}

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            # プロンプトに両方のURLが含まれることを確認
            prompt = kwargs.get("prompt", "")
            assert "https://example1.com" in prompt
            assert "https://example2.com" in prompt
            yield mock_result

        mock_options = None

        result = await fetch_and_summarize(
            mock_query, mock_options, ["https://example1.com", "https://example2.com"]
        )

        assert "# 要約" in result

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_sdk_error(self) -> None:
        """SDKエラー時にRuntimeErrorが発生すること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = True
        mock_result.result = "API error"

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        mock_options = None

        with pytest.raises(RuntimeError, match="要約処理でエラーが発生しました"):
            await fetch_and_summarize(mock_query, mock_options, ["https://example.com"])

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_structured_output_is_none(self) -> None:
        """structured_outputがNoneの場合にRuntimeErrorが発生すること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = None

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            """モックquery関数"""
            yield mock_result

        mock_options = None

        with pytest.raises(RuntimeError, match="構造化出力が取得できませんでした"):
            await fetch_and_summarize(mock_query, mock_options, ["https://example.com"])
