"""pytest設定とモック設定"""

import sys
from unittest.mock import Mock

# テストモジュールのインポート前にSlack SDKをモック化
mock_modules = {
    "aiohttp": Mock(),
    "slack_sdk": Mock(),
    "slack_sdk.web": Mock(),
    "slack_sdk.web.async_client": Mock(),
    "slack_sdk.web.async_base_client": Mock(),
    "slack_sdk.errors": Mock(),
}

for module_name, mock_module in mock_modules.items():
    sys.modules[module_name] = mock_module
