import logging
import os.path
import uuid
from datetime import datetime
from typing import Tuple, BinaryIO, Callable

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.domain.external.file_storage import FileStorage
from app.domain.models.file import File
from app.domain.repositories.uow import IUnitOfWork
from app.infrastructure.storage.oss import OSS

logger = logging.getLogger(__name__)


class OSSFileStorage(FileStorage):
    """基于OSS的文件存储"""

    def __init__(self, oss: OSS, uow_factory: Callable[[], IUnitOfWork], user_id: str) -> None:
        self.oss = oss
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._user_id = user_id

    async def upload_file(self, upload_file: UploadFile) -> File:
        file_id = str(uuid.uuid4())
        _, file_extension = os.path.splitext(upload_file.filename)
        date_path = datetime.now().strftime("%Y/%m/%d")
        oss_key = f"{self._user_id}/{date_path}/{file_id}{file_extension}"

        await run_in_threadpool(
            self.oss.client.put_object,
            oss_key,
            upload_file.file,
        )

        file = File(
            id=file_id,
            user_id=self._user_id,
            filename=upload_file.filename,
            key=oss_key,
            extension=file_extension,
            mime_type=upload_file.content_type or "",
            size=upload_file.size or 0,
        )
        async with self._uow:
            await self._uow.file.save(file)
        return file

    async def download_file(self, file_id: str) -> Tuple[BinaryIO, File]:
        async with self._uow:
            file = await self._uow.file.get_by_id(file_id)
        if not file:
            raise ValueError(f"文件不存在: {file_id}")
        response = await run_in_threadpool(self.oss.client.get_object, file.key)
        return response, file
