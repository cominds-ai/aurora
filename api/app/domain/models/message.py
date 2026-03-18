from typing import Any, List

from pydantic import BaseModel, Field, model_validator


class MessageAttachment(BaseModel):
    """消息附件"""

    filepath: str = ""
    filename: str = ""
    mime_type: str = ""
    url: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_path_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {
                "filepath": value,
                "filename": value.rsplit("/", 1)[-1],
            }
        return value


class Message(BaseModel):
    """用户传递的消息"""
    message: str = ""  # 用户发送的消息
    attachments: List[MessageAttachment] = Field(default_factory=list)  # 用户发送的附件
