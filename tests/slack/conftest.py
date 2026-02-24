"""pytest設定とモック設定"""

import sys
from unittest.mock import Mock

import aiohttp as _real_aiohttp

# テストモジュールのインポート前にSlack SDKをモック化
_mock_aiohttp = Mock()
# isinstance()やexcept節で使われる例外クラスは実物を保持する
_mock_aiohttp.ClientError = _real_aiohttp.ClientError
_mock_aiohttp.ClientConnectionError = _real_aiohttp.ClientConnectionError
_mock_aiohttp.ClientTimeout = _real_aiohttp.ClientTimeout

mock_modules = {
    "aiohttp": _mock_aiohttp,
    "slack_sdk": Mock(),
    "slack_sdk.web": Mock(),
    "slack_sdk.web.async_client": Mock(),
    "slack_sdk.web.async_base_client": Mock(),
    "slack_sdk.errors": Mock(),
}

for module_name, mock_module in mock_modules.items():
    sys.modules[module_name] = mock_module
