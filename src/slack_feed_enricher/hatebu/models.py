from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HatebuBookmark:
    """はてなブックマークの個別ブックマーク"""

    user: str
    comment: str
    timestamp: str

    @property
    def icon_url(self) -> str:
        """はてなプロフィールアイコンのURLを返す"""
        return f"https://cdn.profile-image.st-hatena.com/users/{self.user}/profile.png"


@dataclass
class HatebuEntry:
    """はてなブックマークのエントリー情報"""

    count: int
    bookmarks: list[HatebuBookmark]

    @property
    def comments(self) -> list[HatebuBookmark]:
        """コメントが非空のブックマークのみを返す（空白のみも除外）"""
        return [b for b in self.bookmarks if b.comment.strip()]

    @property
    def comment_count(self) -> int:
        """コメント付きブックマークの件数"""
        return len(self.comments)
