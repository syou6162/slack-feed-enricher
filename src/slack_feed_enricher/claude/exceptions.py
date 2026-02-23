"""Claude Agent SDK連携に関する例外"""


class ClaudeSDKError(Exception):
    """Claude Agent SDK関連のエラーの基底クラス"""


class NoResultMessageError(ClaudeSDKError):
    """ResultMessageが取得できなかった場合のエラー"""


class ClaudeAPIError(ClaudeSDKError):
    """Claude APIでエラーが発生した場合のエラー"""

    def __init__(self, message: str, result: str) -> None:
        """初期化

        Args:
            message: エラーメッセージ
            result: APIから返されたエラー内容
        """
        super().__init__(message)
        self.result = result


class StructuredOutputError(ClaudeSDKError):
    """構造化出力が取得できなかった場合のエラー"""


class QueryTimeoutError(ClaudeSDKError):
    """query()呼び出しがタイムアウトした場合のエラー"""
