"""Slack例外クラスのテスト"""

from slack_feed_enricher.slack.exceptions import SlackAPIError, SlackError


def test_slack_error_is_exception() -> None:
    """SlackErrorがExceptionを継承していること"""
    assert issubclass(SlackError, Exception)


def test_slack_api_error_inherits_slack_error() -> None:
    """SlackAPIErrorがSlackErrorを継承していること"""
    assert issubclass(SlackAPIError, SlackError)


def test_slack_api_error_stores_error_code() -> None:
    """SlackAPIErrorがerror_codeを保持すること"""
    error = SlackAPIError("API error occurred", "channel_not_found")
    assert error.error_code == "channel_not_found"
    assert str(error) == "API error occurred"
