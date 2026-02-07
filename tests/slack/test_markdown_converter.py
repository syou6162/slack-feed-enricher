"""Markdown→Slack mrkdwn変換関数のテスト"""

from slack_feed_enricher.slack.markdown_converter import convert_markdown_to_mrkdwn


class TestConvertMarkdownToMrkdwn:
    """convert_markdown_to_mrkdwn関数のテスト"""

    def test_bold(self) -> None:
        """**bold** → *bold*"""
        result = convert_markdown_to_mrkdwn("**bold**")
        assert result == "*bold*"

    def test_link(self) -> None:
        """[text](url) → <url|text>"""
        result = convert_markdown_to_mrkdwn("[text](https://example.com)")
        assert result == "<https://example.com|text>"

    def test_bullet_list(self) -> None:
        """箇条書き: - item → • item"""
        result = convert_markdown_to_mrkdwn("- item1\n- item2")
        assert result == "• item1\n• item2"

    def test_code_block(self) -> None:
        """コードブロックがそのまま保持される"""
        result = convert_markdown_to_mrkdwn('```python\nprint("hello")\n```')
        assert result == '```python\nprint("hello")\n```'

    def test_table(self) -> None:
        """テーブル: ヘッダーがボールドの簡易テキスト形式"""
        result = convert_markdown_to_mrkdwn("| a | b |\n|---|---|\n| 1 | 2 |")
        assert result == "*a* | *b*\n1 | 2"

    def test_complex_pattern(self) -> None:
        """複合パターン: ボールド + リンク + 箇条書き"""
        md = "**Title**\n\n- [link](https://example.com)\n- plain text"
        result = convert_markdown_to_mrkdwn(md)
        assert "*Title*" in result
        assert "<https://example.com|link>" in result
        assert "• plain text" in result


class TestEscapeSpecialCharacters:
    """Slack特殊文字のエスケープテスト"""

    def test_ampersand_in_text(self) -> None:
        """テキスト内の & → &amp;"""
        result = convert_markdown_to_mrkdwn("A & B")
        assert result == "A &amp; B"

    def test_angle_brackets_in_text(self) -> None:
        """テキスト内の < > → &lt; &gt;"""
        result = convert_markdown_to_mrkdwn("a < b > c")
        assert result == "a &lt; b &gt; c"

    def test_ampersand_in_link_text(self) -> None:
        """リンクテキスト内の & がエスケープされる"""
        result = convert_markdown_to_mrkdwn("[A & B](https://example.com)")
        assert result == "<https://example.com|A &amp; B>"

    def test_angle_bracket_in_link_text(self) -> None:
        """リンクテキスト内の < がエスケープされる"""
        result = convert_markdown_to_mrkdwn("[a < b](https://example.com)")
        assert result == "<https://example.com|a &lt; b>"

    def test_ampersand_in_url_preserved(self) -> None:
        """URL部分の & はそのまま保持"""
        result = convert_markdown_to_mrkdwn("[text](https://example.com?a=1&b=2)")
        assert result == "<https://example.com?a=1&b=2|text>"

    def test_code_block_not_escaped(self) -> None:
        """コードブロック内の特殊文字はエスケープしない"""
        result = convert_markdown_to_mrkdwn("```\na < b & c > d\n```")
        assert "a < b & c > d" in result

    def test_inline_code_not_escaped(self) -> None:
        """インラインコード内の特殊文字はエスケープしない"""
        result = convert_markdown_to_mrkdwn("`a < b & c`")
        assert "a < b & c" in result
