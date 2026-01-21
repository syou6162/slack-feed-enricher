"""Slack API連携に関する例外"""


class SlackError(Exception):
    """Slack API関連のエラーの基底クラス"""


class SlackAPIError(SlackError):
    """Slack APIでエラーが発生した場合のエラー"""

    def __init__(self, message: str, error_code: str) -> None:
        """初期化

        Args:
            message: エラーメッセージ
            error_code: Slack APIから返されたエラーコード
        """
        super().__init__(message)
        self.error_code = error_code
