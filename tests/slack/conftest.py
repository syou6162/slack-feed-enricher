"""pytest設定とモック設定"""

import sys
from collections.abc import Iterator
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(scope="function", autouse=True)
def mock_slack_sdk() -> Iterator[None]:
    """
    Slack SDKの依存関係をこのディレクトリのテストのみでモック化
    """
    mock_modules = {
        "slack_sdk": Mock(),
        "slack_sdk.web": Mock(),
        "slack_sdk.web.async_client": Mock(),
        "slack_sdk.errors": Mock(),
    }

    with patch.dict(sys.modules, mock_modules):
        yield
