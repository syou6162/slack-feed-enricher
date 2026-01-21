from slack_feed_enricher.__main__ import main


def test_main_returns_hello_world() -> None:
    assert main() == "Hello, World!"
