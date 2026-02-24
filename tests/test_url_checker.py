"""url_checker モジュールのテスト"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from slack_feed_enricher.slack.url_checker import check_url_status

_PATCH_TARGET = "slack_feed_enricher.slack.url_checker.aiohttp.ClientSession"


def _make_mock_session(mock_response: AsyncMock) -> AsyncMock:
    """モックされたaiohttp.ClientSessionを作成するヘルパー"""
    mock_session = AsyncMock()
    mock_session.head = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _make_mock_response(*, status: int = 200) -> AsyncMock:
    """モックされたaiohttpレスポンスを作成するヘルパー"""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    return mock_response


class TestCheckUrlStatus:
    """check_url_status関数のテスト"""

    async def test_returns_200_for_ok(self) -> None:
        """200を返すURLに対してステータスコード200が返ること"""
        mock_response = _make_mock_response(status=200)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/article")

        assert result == 200

    async def test_returns_403_for_forbidden(self) -> None:
        """403を返すURLに対してステータスコード403が返ること"""
        mock_response = _make_mock_response(status=403)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/forbidden")

        assert result == 403

    async def test_returns_404_for_not_found(self) -> None:
        """404を返すURLに対してステータスコード404が返ること"""
        mock_response = _make_mock_response(status=404)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/not-found")

        assert result == 404

    async def test_returns_none_on_timeout(self) -> None:
        """タイムアウト時にNoneが返ること"""
        mock_session = AsyncMock()
        mock_session.head = MagicMock(side_effect=TimeoutError)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/slow")

        assert result is None

    async def test_returns_none_on_connection_error(self) -> None:
        """接続エラー時にNoneが返ること"""
        mock_session = AsyncMock()
        mock_session.head = MagicMock(side_effect=aiohttp.ClientConnectionError)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/unreachable")

        assert result is None

    async def test_follows_redirects(self) -> None:
        """リダイレクト追従後の最終ステータスが返ること"""
        mock_response = _make_mock_response(status=200)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/redirect")

        assert result == 200
        call_kwargs = mock_session.head.call_args[1]
        assert call_kwargs.get("allow_redirects") is True

    async def test_uses_timeout(self) -> None:
        """タイムアウトが設定されていること"""
        mock_response = _make_mock_response(status=200)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            await check_url_status("https://example.com")

        call_kwargs = mock_session.head.call_args[1]
        assert "timeout" in call_kwargs
        timeout = call_kwargs["timeout"]
        assert isinstance(timeout, aiohttp.ClientTimeout)

    @pytest.mark.parametrize("status", [403, 404, 410])
    async def test_returns_permanent_failure_statuses(self, status: int) -> None:
        """恒久失敗ステータス（403/404/410）を正しく返すこと"""
        mock_response = _make_mock_response(status=status)
        mock_session = _make_mock_session(mock_response)

        with patch(_PATCH_TARGET, return_value=mock_session):
            result = await check_url_status("https://example.com/article")

        assert result == status
