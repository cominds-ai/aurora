from typing import List

from pydantic import BaseModel, Field


class MessageAttachment(BaseModel):
    """消息附件"""

    filepath: str = ""
    filename: str = ""
    mime_type: str = ""
    url: str = ""


class Message(BaseModel):
    """用户传递的消息"""
    message: str = ""  # 用户发送的消息
    attachments: List[MessageAttachment] = Field(default_factory=list)  # 用户发送的附件
