import uuid

from pydantic import BaseModel, Field


class File(BaseModel):
    """文件信息Domain模型，用于记录 Aurora / 用户上传或生成的文件"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 文件id
    user_id: str = ""  # 所属用户
    filename: str = ""  # 文件名字
    filepath: str = ""  # 文件路径
    key: str = ""  # OSS中的路径
    extension: str = ""  # 扩展名
    mime_type: str = ""  # mime-type类型
    size: int = 0  # 文件大小，单位为字节
