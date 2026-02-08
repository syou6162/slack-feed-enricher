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
    _split_mrkdwn_text,
    build_detail_blocks,
    build_meta_blocks,
    build_summary_blocks,
    build_summary_prompt,
    fetch_and_summarize,
    format_meta_block,
    format_summary_block,
)
from slack_feed_enricher.hatebu.models import HatebuBookmark, HatebuEntry
from slack_feed_enricher.slack.blocks import (
    SlackHeaderBlock,
    SlackRichTextBlock,
    SlackRichTextList,
    SlackRichTextSection,
    SlackSectionBlock,
    SlackTextElement,
    SlackTextObject,
)


class TestStructuredOutputSchema:
    """StructuredOutput Pydanticモデルのスキーマテスト"""

    def test_schema_has_required_top_level_keys(self) -> None:
        """model_json_schema()のトップレベルキーとrequiredが完全一致すること"""
        schema = StructuredOutput.model_json_schema()
        assert set(schema.keys()) == {"$defs", "properties", "required", "title", "type"}
        assert set(schema["required"]) == {"meta", "summary", "detail"}

    def test_schema_has_properties(self) -> None:
        """model_json_schema()のpropertiesがmeta, summary, detailに完全一致すること"""
        schema = StructuredOutput.model_json_schema()
        assert set(schema["properties"].keys()) == {"meta", "summary", "detail"}

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

        expected = EnrichResult(
            meta_text=(
                "*テスト記事*\nURL: https://example.com\n著者: test_author\n"
                "カテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z"
            ),
            meta_blocks=[
                SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="テスト記事")),
                SlackSectionBlock(fields=[
                    SlackTextObject(type="mrkdwn", text="*URL*"),
                    SlackTextObject(type="mrkdwn", text="<https://example.com>"),
                    SlackTextObject(type="mrkdwn", text="*Author*"),
                    SlackTextObject(type="plain_text", text="test_author"),
                    SlackTextObject(type="mrkdwn", text="*Category*"),
                    SlackTextObject(type="plain_text", text="テスト / サブカテゴリ"),
                    SlackTextObject(type="mrkdwn", text="*Published*"),
                    SlackTextObject(type="plain_text", text="2025-01-15T10:30:00Z"),
                ]),
            ],
            summary_text="- ポイント1\n- ポイント2",
            summary_blocks=[
                SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="Summary")),
                SlackRichTextBlock(elements=[
                    SlackRichTextList(style="bullet", elements=[
                        SlackRichTextSection(elements=[SlackTextElement(text="ポイント1")]),
                        SlackRichTextSection(elements=[SlackTextElement(text="ポイント2")]),
                    ]),
                ]),
            ],
            detail_text="*詳細*\n記事の詳細内容",
            detail_blocks=[
                SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="Details")),
                SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text="*詳細*\n記事の詳細内容")),
            ],
        )
        assert result == expected

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

        expected = EnrichResult(
            meta_text=(
                "*テスト記事*\nURL: https://example.com\n著者: test_author\n"
                "カテゴリー: テスト / サブカテゴリ\n投稿日時: 2025-01-15T10:30:00Z"
            ),
            meta_blocks=[
                SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="テスト記事")),
                SlackSectionBlock(fields=[
                    SlackTextObject(type="mrkdwn", text="*URL*"),
                    SlackTextObject(type="mrkdwn", text="<https://example.com>"),
                    SlackTextObject(type="mrkdwn", text="*Author*"),
                    SlackTextObject(type="plain_text", text="test_author"),
                    SlackTextObject(type="mrkdwn", text="*Category*"),
                    SlackTextObject(type="plain_text", text="テスト / サブカテゴリ"),
                    SlackTextObject(type="mrkdwn", text="*Published*"),
                    SlackTextObject(type="plain_text", text="2025-01-15T10:30:00Z"),
                ]),
            ],
            summary_text="- ポイント1",
            summary_blocks=[
                SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="Summary")),
                SlackRichTextBlock(elements=[
                    SlackRichTextList(style="bullet", elements=[
                        SlackRichTextSection(elements=[SlackTextElement(text="ポイント1")]),
                    ]),
                ]),
            ],
            detail_text="*詳細*\n記事の詳細内容",
            detail_blocks=[
                SlackHeaderBlock(text=SlackTextObject(type="plain_text", text="Details")),
                SlackSectionBlock(text=SlackTextObject(type="mrkdwn", text="*詳細*\n記事の詳細内容")),
            ],
        )
        assert result == expected
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

    @pytest.mark.asyncio
    async def test_hatebu_entry_adds_comments_to_detail_and_meta(self) -> None:
        """hatebu_entry付き → detailにコメントセクション、metaにはてブ情報が含まれること"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {
            "meta": {
                "title": "テスト記事",
                "url": "https://example.com",
                "author": None,
                "category_large": None,
                "category_medium": None,
                "published_at": None,
            },
            "summary": {"points": ["ポイント1"]},
            "detail": "# 詳細\n記事の詳細内容",
        }

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            yield mock_result

        entry = HatebuEntry(
            count=3,
            bookmarks=[
                HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30"),
                HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
                HatebuBookmark(user="user3", comment="参考になった", timestamp="2024/01/15 12:00"),
            ],
        )
        result = await fetch_and_summarize(mock_query, "https://example.com", hatebu_entry=entry)

        # detail_textにはてブコメントが含まれること
        assert "はてなブックマークコメント" in result.detail_text
        assert "user1" in result.detail_text
        assert "良い記事" in result.detail_text
        assert "user3" in result.detail_text
        assert "参考になった" in result.detail_text
        # 空コメントのuser2は含まれない
        assert "user2" not in result.detail_text

        # meta_textにはてブ情報が含まれること
        assert "はてなブックマーク: 3 users / 2 comments" in result.meta_text

        # meta_blocksにはてブフィールドが含まれること
        fields_block = result.meta_blocks[1]
        assert isinstance(fields_block, SlackSectionBlock)
        assert fields_block.fields is not None
        hatebu_field_values = [f.text for f in fields_block.fields if "users" in f.text]
        assert len(hatebu_field_values) == 1

    @pytest.mark.asyncio
    async def test_hatebu_entry_none_no_changes(self) -> None:
        """hatebu_entry=None → 従来通りの出力"""
        mock_result = AsyncMock(spec=ResultMessage)
        mock_result.is_error = False
        mock_result.structured_output = {
            "meta": {
                "title": "テスト記事",
                "url": "https://example.com",
                "author": None,
                "category_large": None,
                "category_medium": None,
                "published_at": None,
            },
            "summary": {"points": ["ポイント1"]},
            "detail": "# 詳細\n記事の詳細内容",
        }

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            yield mock_result

        result = await fetch_and_summarize(mock_query, "https://example.com", hatebu_entry=None)
        assert "はてなブックマーク" not in result.detail_text
        assert "はてなブックマーク" not in result.meta_text

    @pytest.mark.asyncio
    async def test_hatebu_detail_blocks_contain_comments(self) -> None:
        """hatebu_entry付き → detail_blocksにもコメントが含まれること"""
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
            "detail": "詳細テキスト",
        }

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            yield mock_result

        entry = HatebuEntry(
            count=1,
            bookmarks=[HatebuBookmark(user="tester", comment="テストコメント", timestamp="2024/01/15 10:30")],
        )
        result = await fetch_and_summarize(mock_query, "https://example.com", hatebu_entry=entry)

        # detail_blocksのテキストにコメントが含まれること
        detail_texts = []
        for block in result.detail_blocks:
            if isinstance(block, SlackSectionBlock) and block.text:
                detail_texts.append(block.text.text)
        all_detail_text = "\n".join(detail_texts)
        assert "tester" in all_detail_text
        assert "テストコメント" in all_detail_text

    @pytest.mark.asyncio
    async def test_hatebu_prompt_includes_file_reference(self) -> None:
        """hatebu_entry付き → プロンプトにファイルパス参照が含まれること"""
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

        received_prompts: list[str] = []

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:
            received_prompts.append(str(kwargs.get("prompt", "")))
            yield mock_result

        entry = HatebuEntry(
            count=1,
            bookmarks=[HatebuBookmark(user="commenter", comment="素晴らしい", timestamp="2024/01/15 10:30")],
        )
        await fetch_and_summarize(mock_query, "https://example.com", hatebu_entry=entry)

        assert len(received_prompts) == 1
        assert ".claude_work/hatebu_comments.txt" in received_prompts[0]
        assert "このコメントを参考に記事を要約してください" in received_prompts[0]

    @pytest.mark.asyncio
    async def test_hatebu_no_comments_no_detail_section(self) -> None:
        """hatebu_entryのコメントが全て空 → detailにコメントセクションが追加されない"""
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
            "detail": "詳細テキスト",
        }

        async def mock_query(**kwargs: object) -> AsyncIterator[object]:  # noqa: ARG001
            yield mock_result

        entry = HatebuEntry(
            count=2,
            bookmarks=[
                HatebuBookmark(user="u1", comment="", timestamp="2024/01/15 10:30"),
                HatebuBookmark(user="u2", comment="   ", timestamp="2024/01/15 11:00"),
            ],
        )
        result = await fetch_and_summarize(mock_query, "https://example.com", hatebu_entry=entry)
        assert "はてなブックマークコメント" not in result.detail_text


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

    def test_hatebu_entry_with_comments(self) -> None:
        """hatebu_entry付き → プロンプトにファイルパス参照が追加される"""

        entry = HatebuEntry(
            count=3,
            bookmarks=[
                HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30"),
                HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
                HatebuBookmark(user="user3", comment="参考になった", timestamp="2024/01/15 12:00"),
            ],
        )
        prompt = build_summary_prompt("https://example.com/article", hatebu_entry=entry)
        assert ".claude_work/hatebu_comments.txt" in prompt
        assert "このコメントを参考に記事を要約してください" in prompt

    def test_hatebu_entry_none_no_hatebu_section(self) -> None:
        """hatebu_entry=None → はてブコメントセクションなし（従来通り）"""
        prompt_with_none = build_summary_prompt("https://example.com/article", hatebu_entry=None)
        prompt_default = build_summary_prompt("https://example.com/article")
        assert prompt_with_none == prompt_default
        assert "はてなブックマークコメント" not in prompt_default

    def test_hatebu_entry_with_no_comments(self) -> None:
        """hatebu_entryのコメントが全て空 → ファイルパス参照が追加されない"""

        entry = HatebuEntry(
            count=2,
            bookmarks=[
                HatebuBookmark(user="user1", comment="", timestamp="2024/01/15 10:30"),
                HatebuBookmark(user="user2", comment="   ", timestamp="2024/01/15 11:00"),
            ],
        )
        prompt = build_summary_prompt("https://example.com/article", hatebu_entry=entry)
        assert ".claude_work/hatebu_comments.txt" not in prompt


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

    def test_hatebu_entry_adds_line(self) -> None:
        """hatebu_entry付き → はてブ情報行が追加されること"""
        meta = {
            "title": "テスト記事",
            "url": "https://example.com/article",
            "author": "taro",
            "category_large": "Tech",
            "category_medium": "Python",
            "published_at": "2025-01-15T10:30:00Z",
        }
        entry = HatebuEntry(
            count=5,
            bookmarks=[
                HatebuBookmark(user="user1", comment="良い", timestamp="2024/01/15 10:30"),
                HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
            ],
        )
        result = format_meta_block(meta, hatebu_entry=entry)
        assert result == (
            "*テスト記事*\n"
            "URL: https://example.com/article\n"
            "著者: taro\n"
            "カテゴリー: Tech / Python\n"
            "投稿日時: 2025-01-15T10:30:00Z\n"
            "はてなブックマーク: 5 users / 1 comments"
        )

    def test_hatebu_entry_none_no_line(self) -> None:
        """hatebu_entry=None → はてブ情報行なし（従来通り）"""
        meta = {
            "title": "テスト",
            "url": "https://example.com",
            "author": None,
            "category_large": None,
            "category_medium": None,
            "published_at": None,
        }
        result_none = format_meta_block(meta, hatebu_entry=None)
        result_default = format_meta_block(meta)
        assert result_none == result_default
        assert "はてなブックマーク" not in result_default

    def test_hatebu_entry_zero_count(self) -> None:
        """hatebu_entry count=0 → 0 users / 0 comments と表示"""
        meta = {
            "title": "テスト",
            "url": "https://example.com",
            "author": None,
            "category_large": None,
            "category_medium": None,
            "published_at": None,
        }
        entry = HatebuEntry(count=0, bookmarks=[])
        result = format_meta_block(meta, hatebu_entry=entry)
        assert "はてなブックマーク: 0 users / 0 comments" in result


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

    def test_all_fields_present(self) -> None:
        """全フィールドが揃ったMetaモデルからheaderブロック + fields sectionの2ブロックが生成されること"""
        meta = Meta(
            title="BigQueryの最適化テクニック",
            url="https://example.com/article",
            author="yamada_taro",
            category_large="データエンジニアリング",
            category_medium="BigQuery",
            published_at="2025-01-15T10:30:00Z",
        )
        blocks = build_meta_blocks(meta)

        assert len(blocks) == 2

        # 1ブロック目: headerブロック（title）
        header_block = blocks[0]
        assert isinstance(header_block, SlackHeaderBlock)
        assert header_block.text == SlackTextObject(type="plain_text", text="BigQueryの最適化テクニック")

        # 2ブロック目: fields section（URL, author, category large/medium結合, published_at）
        fields_block = blocks[1]
        assert isinstance(fields_block, SlackSectionBlock)
        assert fields_block.text is None
        assert fields_block.fields is not None
        assert len(fields_block.fields) == 8  # 4属性 × 2（ラベル+値）
        assert fields_block.fields == [
            SlackTextObject(type="mrkdwn", text="*URL*"),
            SlackTextObject(type="mrkdwn", text="<https://example.com/article>"),
            SlackTextObject(type="mrkdwn", text="*Author*"),
            SlackTextObject(type="plain_text", text="yamada_taro"),
            SlackTextObject(type="mrkdwn", text="*Category*"),
            SlackTextObject(type="plain_text", text="データエンジニアリング / BigQuery"),
            SlackTextObject(type="mrkdwn", text="*Published*"),
            SlackTextObject(type="plain_text", text="2025-01-15T10:30:00Z"),
        ]

    def test_all_optional_fields_none(self) -> None:
        """全Optionalフィールドがnullの場合、headerブロック + URLのみのfields sectionの2ブロックが生成されること"""
        meta = Meta(
            title="無名の記事",
            url="https://example.com/anonymous",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        blocks = build_meta_blocks(meta)

        assert len(blocks) == 2
        assert isinstance(blocks[0], SlackHeaderBlock)
        assert blocks[0].text == SlackTextObject(type="plain_text", text="無名の記事")
        fields_block = blocks[1]
        assert isinstance(fields_block, SlackSectionBlock)
        assert fields_block.fields is not None
        assert len(fields_block.fields) == 2  # URLのみ
        assert fields_block.fields == [
            SlackTextObject(type="mrkdwn", text="*URL*"),
            SlackTextObject(type="mrkdwn", text="<https://example.com/anonymous>"),
        ]

    def test_partial_optional_fields(self) -> None:
        """一部のOptionalフィールドのみがある場合、URL + 存在する項目のみがfieldsに含まれること"""
        meta = Meta(
            title="著者ありカテゴリなし",
            url="https://example.com/partial",
            author="taro",
            category_large=None,
            category_medium=None,
            published_at="2025-01-15T10:30:00Z",
        )
        blocks = build_meta_blocks(meta)

        assert len(blocks) == 2

        fields_block = blocks[1]
        assert fields_block.fields is not None
        assert len(fields_block.fields) == 6  # 3属性（URL, author, published_at） × 2
        assert fields_block.fields == [
            SlackTextObject(type="mrkdwn", text="*URL*"),
            SlackTextObject(type="mrkdwn", text="<https://example.com/partial>"),
            SlackTextObject(type="mrkdwn", text="*Author*"),
            SlackTextObject(type="plain_text", text="taro"),
            SlackTextObject(type="mrkdwn", text="*Published*"),
            SlackTextObject(type="plain_text", text="2025-01-15T10:30:00Z"),
        ]

    def test_category_large_and_medium(self) -> None:
        """category_largeとcategory_mediumが両方ある場合、結合表示されること"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author=None,
            category_large="データエンジニアリング",
            category_medium="BigQuery",
            published_at=None,
        )
        blocks = build_meta_blocks(meta)
        fields_block = blocks[1]
        assert SlackTextObject(type="plain_text", text="データエンジニアリング / BigQuery") in fields_block.fields

    def test_category_large_only(self) -> None:
        """category_largeのみの場合、largeのみが表示されること"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author=None,
            category_large="データエンジニアリング",
            category_medium=None,
            published_at=None,
        )
        blocks = build_meta_blocks(meta)
        fields_block = blocks[1]
        assert SlackTextObject(type="plain_text", text="データエンジニアリング") in fields_block.fields

    def test_category_medium_only(self) -> None:
        """category_mediumのみの場合、mediumのみが表示されること"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author=None,
            category_large=None,
            category_medium="BigQuery",
            published_at=None,
        )
        blocks = build_meta_blocks(meta)
        fields_block = blocks[1]
        assert SlackTextObject(type="plain_text", text="BigQuery") in fields_block.fields

    def test_title_truncated_at_150_chars(self) -> None:
        """150文字を超えるタイトルがトリミングされること"""
        long_title = "あ" * 200
        meta = Meta(
            title=long_title,
            url="https://example.com",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        blocks = build_meta_blocks(meta)
        header_block = blocks[0]
        assert isinstance(header_block, SlackHeaderBlock)
        assert header_block.text.text == "あ" * 150
        assert len(header_block.text.text) == 150

    def test_title_exactly_150_chars_not_truncated(self) -> None:
        """ちょうど150文字のタイトルはトリミングされないこと"""
        title_150 = "あ" * 150
        meta = Meta(
            title=title_150,
            url="https://example.com",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        blocks = build_meta_blocks(meta)
        header_block = blocks[0]
        assert header_block.text.text == title_150

    def test_hatebu_entry_adds_bookmark_field(self) -> None:
        """hatebu_entry付き → fieldsにはてブ情報が1フィールド（2要素）追加されること"""
        meta = Meta(
            title="テスト記事",
            url="https://example.com/article",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        entry = HatebuEntry(
            count=5,
            bookmarks=[
                HatebuBookmark(user="user1", comment="良い", timestamp="2024/01/15 10:30"),
                HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
                HatebuBookmark(user="user3", comment="参考になった", timestamp="2024/01/15 12:00"),
            ],
        )
        blocks = build_meta_blocks(meta, hatebu_entry=entry)
        fields_block = blocks[1]
        assert isinstance(fields_block, SlackSectionBlock)
        assert fields_block.fields is not None
        # URL(2) + はてブ(2) = 4要素
        assert len(fields_block.fields) == 4
        assert SlackTextObject(type="mrkdwn", text="*Hatena Bookmark*") in fields_block.fields
        assert SlackTextObject(type="plain_text", text="\U0001f4da 5 users / \U0001f4ac 2 comments") in fields_block.fields

    def test_hatebu_entry_with_all_meta_fields(self) -> None:
        """全メタフィールド + hatebu_entry → fields上限10要素以内で収まること"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author="taro",
            category_large="Tech",
            category_medium="Python",
            published_at="2025-01-15T10:30:00Z",
        )
        entry = HatebuEntry(
            count=10,
            bookmarks=[HatebuBookmark(user="u1", comment="good", timestamp="2024/01/15 10:30")],
        )
        blocks = build_meta_blocks(meta, hatebu_entry=entry)
        fields_block = blocks[1]
        assert fields_block.fields is not None
        # URL(2) + Author(2) + Category(2) + Published(2) + Hatena(2) = 10要素（Slack上限ちょうど）
        assert len(fields_block.fields) == 10

    def test_hatebu_entry_none_no_bookmark_field(self) -> None:
        """hatebu_entry=None → はてブフィールドが追加されないこと（従来通り）"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        blocks = build_meta_blocks(meta, hatebu_entry=None)
        fields_block = blocks[1]
        assert fields_block.fields is not None
        assert len(fields_block.fields) == 2  # URLのみ

    def test_hatebu_entry_zero_count(self) -> None:
        """hatebu_entry count=0 → 0 users / 0 comments と表示されること"""
        meta = Meta(
            title="テスト",
            url="https://example.com",
            author=None,
            category_large=None,
            category_medium=None,
            published_at=None,
        )
        entry = HatebuEntry(count=0, bookmarks=[])
        blocks = build_meta_blocks(meta, hatebu_entry=entry)
        fields_block = blocks[1]
        assert fields_block.fields is not None
        assert len(fields_block.fields) == 4  # URL(2) + Hatena(2)
        assert SlackTextObject(type="plain_text", text="\U0001f4da 0 users / \U0001f4ac 0 comments") in fields_block.fields


class TestBuildSummaryBlocks:
    """build_summary_blocks関数のテスト"""

    def test_multiple_points(self) -> None:
        """複数pointsのSummaryモデルからheaderブロック+rich_text_listの2ブロックが生成されること"""
        summary = Summary(points=["ポイント1", "ポイント2", "ポイント3"])
        blocks = build_summary_blocks(summary)

        assert len(blocks) == 2

        # 1ブロック目: headerブロック
        header_block = blocks[0]
        assert isinstance(header_block, SlackHeaderBlock)
        assert header_block.text == SlackTextObject(type="plain_text", text="Summary")

        # 2ブロック目: rich_textブロック
        rich_text_block = blocks[1]
        assert isinstance(rich_text_block, SlackRichTextBlock)
        assert len(rich_text_block.elements) == 1
        rich_text_list = rich_text_block.elements[0]
        assert isinstance(rich_text_list, SlackRichTextList)
        assert rich_text_list.style == "bullet"
        assert len(rich_text_list.elements) == 3
        assert rich_text_list.elements[0] == SlackRichTextSection(
            elements=[SlackTextElement(text="ポイント1")]
        )
        assert rich_text_list.elements[1] == SlackRichTextSection(
            elements=[SlackTextElement(text="ポイント2")]
        )
        assert rich_text_list.elements[2] == SlackRichTextSection(
            elements=[SlackTextElement(text="ポイント3")]
        )

    def test_single_point(self) -> None:
        """1ポイントのSummaryモデルでもheader+rich_textの2ブロックが生成されること"""
        summary = Summary(points=["唯一のポイント"])
        blocks = build_summary_blocks(summary)

        assert len(blocks) == 2
        assert isinstance(blocks[0], SlackHeaderBlock)
        rich_text_block = blocks[1]
        assert isinstance(rich_text_block, SlackRichTextBlock)
        rich_text_list = rich_text_block.elements[0]
        assert rich_text_list.style == "bullet"
        assert len(rich_text_list.elements) == 1
        assert rich_text_list.elements[0] == SlackRichTextSection(
            elements=[SlackTextElement(text="唯一のポイント")]
        )


class TestBuildDetailBlocks:
    """build_detail_blocks関数のテスト"""

    def test_returns_header_and_section_with_mrkdwn_conversion(self) -> None:
        """Markdownがmrkdwnに変換されてsectionブロックに格納されること"""
        detail = "**bold** and [link](https://example.com)"
        blocks = build_detail_blocks(detail)

        assert len(blocks) == 2

        # 1ブロック目: headerブロック
        header_block = blocks[0]
        assert isinstance(header_block, SlackHeaderBlock)
        assert header_block.text == SlackTextObject(type="plain_text", text="Details")

        # 2ブロック目: mrkdwn変換後のsectionブロック
        detail_block = blocks[1]
        assert isinstance(detail_block, SlackSectionBlock)
        assert detail_block.text == SlackTextObject(
            type="mrkdwn",
            text="*bold* and <https://example.com|link>",
        )

    def test_split_at_newline_boundary(self) -> None:
        """3000文字超のdetailが改行位置で分割されること"""
        # 2900文字 + 改行 + 200文字 = 3101文字（変換後）
        line1 = "あ" * 2900
        line2 = "い" * 200
        detail = f"{line1}\n{line2}"
        blocks = build_detail_blocks(detail)

        assert len(blocks) == 3
        assert isinstance(blocks[0], SlackHeaderBlock)
        # 改行位置で分割されるため、1つ目は2900文字
        assert blocks[1].text.text == line1
        # 2つ目は200文字
        assert blocks[2].text.text == line2

    def test_split_long_text_without_newlines(self) -> None:
        """改行のない3000文字超のdetailが文字数ベースで強制分割されること"""
        detail = "あ" * 4000
        blocks = build_detail_blocks(detail)

        assert len(blocks) == 3
        assert isinstance(blocks[0], SlackHeaderBlock)
        assert len(blocks[1].text.text) == 3000
        assert len(blocks[2].text.text) == 1000

    def test_detail_exactly_3000_chars_single_section(self) -> None:
        """ちょうど3000文字のdetailは分割されないこと"""
        detail = "あ" * 3000
        blocks = build_detail_blocks(detail)

        assert len(blocks) == 2
        assert isinstance(blocks[0], SlackHeaderBlock)
        assert isinstance(blocks[1], SlackSectionBlock)
        assert len(blocks[1].text.text) == 3000

    def test_entity_not_split(self) -> None:
        """&amp;エンティティの途中で分割されないこと"""
        # 2998文字 + "&amp;" (5文字) = 3003文字
        prefix = "あ" * 2998
        detail = f"{prefix}A & B"  # Markdown入力。変換後: prefix + "A &amp; B" = 2998 + 8 = 3006文字
        blocks = build_detail_blocks(detail)

        # 分割されるが、&amp;の途中では切れない
        assert len(blocks) >= 2
        for block in blocks[1:]:
            text = block.text.text
            # &amp; が途中で切れていないことを確認
            assert "&am" not in text or "&amp;" in text

    def test_multiple_sections_over_3000(self) -> None:
        """7000文字超のdetailが適切に複数sectionに分割されること"""
        # 2500文字 + 改行 + 2500文字 + 改行 + 2500文字 = 7502文字
        line = "あ" * 2500
        detail = f"{line}\n{line}\n{line}"
        blocks = build_detail_blocks(detail)

        assert isinstance(blocks[0], SlackHeaderBlock)
        # 全sectionブロックが3000文字以下
        for block in blocks[1:]:
            assert isinstance(block, SlackSectionBlock)
            assert len(block.text.text) <= 3000

    def test_escape_applied_in_detail(self) -> None:
        """detailのテキスト内の&, <, >がエスケープされること"""
        detail = "a < b & c > d"
        blocks = build_detail_blocks(detail)

        assert blocks[1].text.text == "a &lt; b &amp; c &gt; d"


class TestSplitMrkdwnText:
    """_split_mrkdwn_text関数のテスト（構文保護）"""

    def test_code_block_not_split(self) -> None:
        """コードブロックが分割境界をまたがないこと（ブロック再オープン方式）"""
        # テキスト + コードブロック（合計3000文字超）
        prefix = "あ" * 100 + "\n"
        code_block = "```\n" + "x" * 3000 + "\n```"
        text = prefix + code_block
        chunks = _split_mrkdwn_text(text)

        # コードブロックが分割された場合、各チャンクで```が対になっていること
        for chunk in chunks:
            count = chunk.count("```")
            assert count % 2 == 0, f"コードブロックの```が対になっていない: {chunk[:100]}..."

    def test_slack_link_not_split(self) -> None:
        """Slackリンク<url|text>が分割境界をまたがないこと"""
        # 2990文字 + 長いリンク（合計3000文字超）
        prefix = "あ" * 2990
        link = "<https://example.com/very/long/path|リンクテキスト>"
        text = prefix + link
        chunks = _split_mrkdwn_text(text)

        # リンクが途中で切れていないこと
        for chunk in chunks:
            # < の数と > の数が一致すること（リンク構文が壊れていない）
            open_count = chunk.count("<")
            close_count = chunk.count(">")
            assert open_count == close_count, f"リンク構文が壊れている: {chunk[-100:]}"

    def test_code_block_reopen_across_chunks(self) -> None:
        """コードブロックが分割された場合、閉じて次チャンクで再オープンすること"""
        code_content = "x" * 5000
        text = f"```\n{code_content}\n```"
        chunks = _split_mrkdwn_text(text)

        # 複数チャンクに分割されること
        assert len(chunks) >= 2
        # 各チャンクで```が対になっていること
        for chunk in chunks:
            count = chunk.count("```")
            assert count % 2 == 0, "コードブロックの```が対になっていない"

    def test_code_block_chunks_within_3000_chars(self) -> None:
        """コードブロック分割時に閉じ/再オープンフェンス込みで各チャンクが3000文字以内であること"""
        # 改行なしの長いコードブロック（5000文字超）
        code_content = "x" * 5000
        text = f"```\n{code_content}\n```"
        chunks = _split_mrkdwn_text(text)

        # 各チャンクが3000文字以内であること
        for i, chunk in enumerate(chunks):
            assert len(chunk) <= 3000, (
                f"チャンク{i}が3000文字を超えている: {len(chunk)}文字"
            )

    def test_slack_link_at_chunk_start_not_split(self) -> None:
        """チャンク先頭のSlackリンクが分割されないこと（link_start==0のケース）

        2チャンク目の先頭がSlackリンクで始まり、そのリンク内で
        split_posが来る場合に、link_start==0でも調整されること。
        """
        # 1チャンク目で改行分割される部分（2999文字+改行）
        first_part = "あ" * 2999 + "\n"
        # 2チャンク目の先頭がSlackリンク（2996文字）+ 末尾テキストで合計3000文字超
        url = "https://example.com/" + "a" * 2970
        link = f"<{url}|テスト>"  # 2996文字
        text = first_part + link + "末尾テキスト"

        chunks = _split_mrkdwn_text(text)

        # リンクが途中で切れていないこと
        for chunk in chunks:
            open_count = chunk.count("<")
            close_count = chunk.count(">")
            assert open_count == close_count, f"リンク構文が壊れている: {chunk[:100]}..."

    def test_oversized_slack_link_force_split_within_limit(self) -> None:
        """3000文字を超えるSlackリンクが強制分割され、各チャンクが3000文字以内であること"""
        # リンク全体が3000文字超（異常に長いURL）
        url = "https://example.com/" + "a" * 3500
        link = f"<{url}|テスト>"
        text = link

        chunks = _split_mrkdwn_text(text)

        # 各チャンクが3000文字以内であること（Slack投稿エラー回避が最優先）
        for i, chunk in enumerate(chunks):
            assert len(chunk) <= 3000, (
                f"チャンク{i}が3000文字を超えている: {len(chunk)}文字"
            )

    def test_will_split_in_code_recalculated_after_adjustment(self) -> None:
        """split_pos調整後にwill_split_in_codeが再計算されること

        エンティティ(&amp;)がコードブロック直前にあり、エンティティ保護で
        split_posがコードブロック外に移動した場合、誤って```が付与されないこと。

        構成: prefix(2993) + &amp;(5文字, 2993-2997) + ```code```(2998-)
        effective_max=3000, pos 3000はコード内 → will_split_in_code=True
        close_cost=4, split_pos=2996 → &amp;の途中 → 2993に調整
        2993はコード外 → will_split_in_codeを再計算しないと誤って```が付与される
        """
        prefix = "x" * 2993
        entity = "&amp;"  # 5文字（2993-2997）
        code_content = "y" * 100
        code = f"```{code_content}```"  # コードブロック（2998-）
        text = prefix + entity + code

        chunks = _split_mrkdwn_text(text)

        # 最初のチャンクはprefix + entityまでのはずで、コードブロック外
        # will_split_in_codeが再計算されていれば```は付与されない
        first_chunk = chunks[0]
        assert "```" not in first_chunk, (
            f"コードブロック外のチャンクに```が付与されている: {first_chunk[-50:]}"
        )

    def test_newline_inside_code_block_not_used_for_split(self) -> None:
        """コードブロック内の改行が分割ポイントとして使われないこと"""
        prefix = "あ" * 2000 + "\n"
        # コードブロック内に改行が多数あるケース（合計3000文字超）
        code_lines = "\n".join(["line " + str(i) for i in range(200)])
        code_block = f"```\n{code_lines}\n```"
        text = prefix + code_block

        chunks = _split_mrkdwn_text(text)

        # 各チャンクでコードブロックが壊れていないこと
        for chunk in chunks:
            count = chunk.count("```")
            assert count % 2 == 0, "コードブロック内の改行で分割された"
