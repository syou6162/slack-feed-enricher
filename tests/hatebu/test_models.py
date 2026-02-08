from __future__ import annotations

from slack_feed_enricher.hatebu.models import HatebuBookmark, HatebuEntry


class TestHatebuBookmark:
    """HatebuBookmark dataclassのテスト"""

    def test_create_bookmark(self) -> None:
        """ブックマークインスタンスが正しく生成されること"""
        bookmark = HatebuBookmark(
            user="testuser",
            comment="良い記事",
            timestamp="2024/01/15 10:30",
        )
        assert bookmark.user == "testuser"
        assert bookmark.comment == "良い記事"
        assert bookmark.timestamp == "2024/01/15 10:30"

    def test_icon_url(self) -> None:
        """icon_urlがはてなプロフィールアイコンURLを返すこと"""
        bookmark = HatebuBookmark(
            user="testuser",
            comment="良い記事",
            timestamp="2024/01/15 10:30",
        )
        assert bookmark.icon_url == "https://cdn.profile-image.st-hatena.com/users/testuser/profile.png"

    def test_create_bookmark_with_empty_comment(self) -> None:
        """空コメントのブックマークが生成できること"""
        bookmark = HatebuBookmark(
            user="testuser",
            comment="",
            timestamp="2024/01/15 10:30",
        )
        assert bookmark.comment == ""


class TestHatebuEntry:
    """HatebuEntry dataclassのテスト"""

    def test_create_entry(self) -> None:
        """エントリーインスタンスが正しく生成されること"""
        bookmarks = [
            HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30"),
            HatebuBookmark(user="user2", comment="参考になった", timestamp="2024/01/15 11:00"),
        ]
        entry = HatebuEntry(count=2, bookmarks=bookmarks)
        assert entry.count == 2
        assert len(entry.bookmarks) == 2

    def test_comment_count_returns_non_empty_comments_count(self) -> None:
        """comment_countが空コメントを除外した件数を返すこと"""
        bookmarks = [
            HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30"),
            HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
            HatebuBookmark(user="user3", comment="参考になった", timestamp="2024/01/15 12:00"),
        ]
        entry = HatebuEntry(count=3, bookmarks=bookmarks)
        assert entry.comment_count == 2

    def test_comment_count_with_all_empty_comments(self) -> None:
        """全ブックマークのコメントが空の場合、comment_countが0を返すこと"""
        bookmarks = [
            HatebuBookmark(user="user1", comment="", timestamp="2024/01/15 10:30"),
            HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
        ]
        entry = HatebuEntry(count=2, bookmarks=bookmarks)
        assert entry.comment_count == 0

    def test_comments_returns_only_non_empty_bookmarks(self) -> None:
        """commentsプロパティが空コメントのブックマークを除外すること"""
        bookmarks = [
            HatebuBookmark(user="user1", comment="良い記事", timestamp="2024/01/15 10:30"),
            HatebuBookmark(user="user2", comment="", timestamp="2024/01/15 11:00"),
            HatebuBookmark(user="user3", comment="参考になった", timestamp="2024/01/15 12:00"),
        ]
        entry = HatebuEntry(count=3, bookmarks=bookmarks)
        comments = entry.comments
        assert len(comments) == 2
        assert comments[0].user == "user1"
        assert comments[1].user == "user3"

    def test_comments_excludes_whitespace_only_comments(self) -> None:
        """空白のみのコメントも除外されること"""
        bookmarks = [
            HatebuBookmark(user="user1", comment="   ", timestamp="2024/01/15 10:30"),
            HatebuBookmark(user="user2", comment="\t\n", timestamp="2024/01/15 11:00"),
            HatebuBookmark(user="user3", comment="有効なコメント", timestamp="2024/01/15 12:00"),
        ]
        entry = HatebuEntry(count=3, bookmarks=bookmarks)
        assert entry.comment_count == 1
        assert entry.comments[0].user == "user3"

    def test_comments_with_no_bookmarks(self) -> None:
        """ブックマーク0件の場合のcommentsとcomment_count"""
        entry = HatebuEntry(count=0, bookmarks=[])
        assert entry.comment_count == 0
        assert entry.comments == []

    def test_count_preserves_total_bookmark_count(self) -> None:
        """countフィールドが空コメント含む全ブクマ数を保持すること"""
        bookmarks = [
            HatebuBookmark(user="user1", comment="", timestamp="2024/01/15 10:30"),
            HatebuBookmark(user="user2", comment="コメント", timestamp="2024/01/15 11:00"),
        ]
        entry = HatebuEntry(count=5, bookmarks=bookmarks)
        # countはAPI返却値をそのまま保持（bookmarksの長さとは異なる場合がある）
        assert entry.count == 5
        assert entry.comment_count == 1
