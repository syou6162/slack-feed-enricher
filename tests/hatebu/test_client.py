from __future__ import annotations

from typing import runtime_checkable
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp

from slack_feed_enricher.hatebu.client import AiohttpHatebuClient, HatebuClient
from slack_feed_enricher.hatebu.models import HatebuBookmark

_PATCH_TARGET = "slack_feed_enricher.hatebu.client.aiohttp.ClientSession"


def _make_mock_session(mock_response: AsyncMock) -> AsyncMock:
    """モックされたaiohttp.ClientSessionを作成するヘルパー"""
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _make_mock_response(*, status: int = 200, json_data: object = None) -> AsyncMock:
    """モックされたaiohttp レスポンスを作成するヘルパー"""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    return mock_response


class TestHatebuClientProtocol:
    """HatebuClient Protocolのテスト"""

    def test_protocol_is_runtime_checkable(self) -> None:
        """Protocolがruntime_checkableであること"""
        assert runtime_checkable(HatebuClient)

    def test_aiohttp_client_implements_protocol(self) -> None:
        """AiohttpHatebuClientがHatebuClient Protocolを実装していること"""
        client = AiohttpHatebuClient()
        assert isinstance(client, HatebuClient)


class TestAiohttpHatebuClient:
    """AiohttpHatebuClientのテスト"""

    async def test_fetch_entry_parses_json_response(self) -> None:
        """JSONレスポンスをHatebuEntryに変換すること"""
        json_data = {
            "count": 3,
            "bookmarks": [
                {"user": "user1", "comment": "良い記事", "timestamp": "2024/01/15 10:30", "tags": ["tech"]},
                {"user": "user2", "comment": "", "timestamp": "2024/01/15 11:00", "tags": []},
                {"user": "user3", "comment": "参考になった", "timestamp": "2024/01/15 12:00", "tags": ["python"]},
            ],
        }

        mock_response = _make_mock_response(json_data=json_data)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            client = AiohttpHatebuClient()
            result = await client.fetch_entry("https://example.com/article")

        assert result is not None
        assert result.count == 3
        assert len(result.bookmarks) == 3
        assert result.bookmarks[0] == HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30")
        assert result.bookmarks[1] == HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00")
        assert result.bookmarks[2] == HatebuBookmark(user="user3", comment="参考になった", timestamp="2024/01/15 12:00")

    async def test_fetch_entry_returns_none_on_404(self) -> None:
        """404レスポンスでNoneが返ること"""
        mock_response = _make_mock_response(status=404)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            client = AiohttpHatebuClient()
            result = await client.fetch_entry("https://example.com/not-found")

        assert result is None

    async def test_fetch_entry_returns_none_on_null_response(self) -> None:
        """レスポンスがnullの場合Noneが返ること"""
        mock_response = _make_mock_response(json_data=None)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            client = AiohttpHatebuClient()
            result = await client.fetch_entry("https://example.com/null-entry")

        assert result is None

    async def test_fetch_entry_returns_entry_with_zero_count(self) -> None:
        """count=0のレスポンスでHatebuEntry(count=0)が返ること"""
        json_data = {"count": 0, "bookmarks": []}
        mock_response = _make_mock_response(json_data=json_data)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            client = AiohttpHatebuClient()
            result = await client.fetch_entry("https://example.com/zero-bookmarks")

        assert result is not None
        assert result.count == 0
        assert result.bookmarks == []

    async def test_fetch_entry_encodes_url_with_special_characters(self) -> None:
        """?や&を含むURLが正しくエンコードされること"""
        json_data = {"count": 1, "bookmarks": []}
        mock_response = _make_mock_response(json_data=json_data)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            client = AiohttpHatebuClient()
            await client.fetch_entry("https://example.com/page?key=value&foo=bar")

        call_args = mock_session.get.call_args
        called_url = call_args[0][0]
        assert "https%3A%2F%2Fexample.com%2Fpage%3Fkey%3Dvalue%26foo%3Dbar" in called_url

    async def test_fetch_entry_uses_timeout(self) -> None:
        """タイムアウトが設定されていること"""
        json_data = {"count": 1, "bookmarks": []}
        mock_response = _make_mock_response(json_data=json_data)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session) as mock_cls:
            client = AiohttpHatebuClient()
            await client.fetch_entry("https://example.com")

        call_kwargs = mock_cls.call_args[1]
        assert "timeout" in call_kwargs
        timeout = call_kwargs["timeout"]
        assert isinstance(timeout, aiohttp.ClientTimeout)
        assert timeout.total == 10

    async def test_fetch_entry_returns_none_on_timeout_error(self) -> None:
        """タイムアウト時にNoneが返ること"""
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_session.get = MagicMock(side_effect=TimeoutError)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(_PATCH_TARGET, return_value=mock_session):
            client = AiohttpHatebuClient()
            result = await client.fetch_entry("https://example.com/slow")

        assert result is None
