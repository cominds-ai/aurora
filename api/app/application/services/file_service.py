from typing import Tuple, BinaryIO, Callable

from fastapi import UploadFile

from app.application.errors.exceptions import NotFoundError
from app.domain.external.file_storage import FileStorage
from app.domain.models.file import File
from app.domain.repositories.uow import IUnitOfWork


class FileService:
    """Aurora文件系统服务"""

    def __init__(
            self,
            uow_factory: Callable[[], IUnitOfWork],
            file_storage: FileStorage,
            user_id: str,
    ) -> None:
        """构造函数，完成文件服务的初始化"""
        self.file_storage = file_storage
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._user_id = user_id

    async def upload_file(self, upload_file: UploadFile) -> File:
        """将传递的文件上传到阿里云 OSS 并记录上传数据"""
        return await self.file_storage.upload_file(upload_file=upload_file)

    async def get_file_info(self, file_id: str) -> File:
        """根据传递的文件id获取文件信息"""
        async with self._uow:
            file = await self._uow.file.get_by_id(file_id)
        if not file or file.user_id != self._user_id:
            raise NotFoundError(f"该文件[{file_id}]不存在")
        return file

    async def download_file(self, file_id: str) -> Tuple[BinaryIO, File]:
        """根据传递的文件id下载文件"""
        await self.get_file_info(file_id)
        return await self.file_storage.download_file(file_id)
