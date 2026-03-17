import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class User(BaseModel):
    """用户领域模型"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    display_name: str
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
