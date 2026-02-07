"""Slack Block Kit型定義"""

from typing import Literal

from pydantic import BaseModel


class SlackTextObject(BaseModel, frozen=True):
    type: Literal["plain_text", "mrkdwn"]
    text: str


class SlackSectionBlock(BaseModel, frozen=True):
    type: Literal["section"] = "section"
    text: SlackTextObject | None = None
    fields: list[SlackTextObject] | None = None


class SlackDividerBlock(BaseModel, frozen=True):
    type: Literal["divider"] = "divider"


class SlackHeaderBlock(BaseModel, frozen=True):
    type: Literal["header"] = "header"
    text: SlackTextObject


SlackBlock = SlackSectionBlock | SlackDividerBlock | SlackHeaderBlock
