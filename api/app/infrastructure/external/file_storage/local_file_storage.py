import base64
import io
import mimetypes
import os.path
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable, Tuple

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.domain.external.file_storage import FileStorage
from app.domain.models.file import File
from app.domain.repositories.uow import IUnitOfWork


class LocalFileStorage(FileStorage):
    """本地磁盘文件存储，供未配置OSS的开发环境使用"""

    def __init__(
            self,
            uow_factory: Callable[[], IUnitOfWork],
            user_id: str,
            storage_root: Path | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._user_id = user_id
        self._storage_root = storage_root or Path(__file__).resolve().parents[4] / "tmp" / "uploads"

    async def upload_file(self, upload_file: UploadFile) -> File:
        file_id = str(uuid.uuid4())
        filename = upload_file.filename or file_id
        _, file_extension = os.path.splitext(filename)
        date_path = datetime.now().strftime("%Y/%m/%d")
        relative_path = Path(self._user_id) / date_path / f"{file_id}{file_extension}"
        absolute_path = self._storage_root / relative_path

        await run_in_threadpool(self._write_upload_file, upload_file.file, absolute_path)

        file = File(
            id=file_id,
            user_id=self._user_id,
            filename=filename,
            key=relative_path.as_posix(),
            extension=file_extension,
            mime_type=upload_file.content_type or self._guess_mime_type(filename),
            size=upload_file.size or absolute_path.stat().st_size,
        )
        async with self._uow:
            await self._uow.file.save(file)
        return file

    async def download_file(self, file_id: str) -> Tuple[BinaryIO, File]:
        async with self._uow:
            file = await self._uow.file.get_by_id(file_id)
        if not file:
            raise ValueError(f"文件不存在: {file_id}")

        absolute_path = self._resolve_path(file)
        if not absolute_path.exists():
            raise ValueError(f"文件不存在: {file_id}")

        content = await run_in_threadpool(absolute_path.read_bytes)
        return io.BytesIO(content), file

    async def get_file_url(self, file: File) -> str:
        mime_type = file.mime_type or self._guess_mime_type(file.filename)
        if not mime_type.startswith("image/"):
            return ""

        absolute_path = self._resolve_path(file)
        if not absolute_path.exists():
            return ""

        content = await run_in_threadpool(absolute_path.read_bytes)
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _resolve_path(self, file: File) -> Path:
        return self._storage_root / file.key

    @staticmethod
    def _guess_mime_type(filename: str) -> str:
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"

    @staticmethod
    def _write_upload_file(file_data: BinaryIO, absolute_path: Path) -> None:
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        file_data.seek(0)
        with absolute_path.open("wb") as output:
            shutil.copyfileobj(file_data, output)
        file_data.seek(0)
