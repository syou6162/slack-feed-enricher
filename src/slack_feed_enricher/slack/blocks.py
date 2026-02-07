"""Slack Block Kit型定義"""

from typing import Literal

from pydantic import BaseModel


class SlackTextObject(BaseModel, frozen=True):
    type: Literal["plain_text", "mrkdwn"]
    text: str


class SlackSectionBlock(BaseModel, frozen=True):
    type: Literal["section"] = "section"
    text: SlackTextObject


class SlackDividerBlock(BaseModel, frozen=True):
    type: Literal["divider"] = "divider"


SlackBlock = SlackSectionBlock | SlackDividerBlock
