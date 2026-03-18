from typing import Protocol, Tuple, BinaryIO

from fastapi import UploadFile

from app.domain.models.file import File


class FileStorage(Protocol):
    """文件存储桶协议"""

    async def upload_file(self, upload_file: UploadFile) -> File:
        """根据传递的文件源上传文件后返回文件信息"""
        ...

    async def download_file(self, file_id: str) -> Tuple[BinaryIO, File]:
        """根据传递的文件id下载文件，并返回文件源+文件信息"""
        ...

    async def get_file_url(self, file: File) -> str:
        """返回模型或前端可消费的文件URL；无法直接暴露时返回空字符串"""
        ...
