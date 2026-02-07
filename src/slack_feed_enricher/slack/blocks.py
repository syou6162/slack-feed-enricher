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


class SlackTextElement(BaseModel, frozen=True):
    type: Literal["text"] = "text"
    text: str


class SlackRichTextSection(BaseModel, frozen=True):
    type: Literal["rich_text_section"] = "rich_text_section"
    elements: list[SlackTextElement]


class SlackRichTextList(BaseModel, frozen=True):
    type: Literal["rich_text_list"] = "rich_text_list"
    style: Literal["bullet", "ordered"]
    elements: list[SlackRichTextSection]
    indent: int | None = None


class SlackRichTextBlock(BaseModel, frozen=True):
    type: Literal["rich_text"] = "rich_text"
    elements: list[SlackRichTextList]


SlackBlock = SlackSectionBlock | SlackDividerBlock | SlackHeaderBlock | SlackRichTextBlock
