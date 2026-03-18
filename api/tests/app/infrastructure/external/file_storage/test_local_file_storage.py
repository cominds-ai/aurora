import asyncio
import io
from pathlib import Path

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.domain.models.file import File
from app.infrastructure.external.file_storage.local_file_storage import LocalFileStorage


class FakeFileRepository:
    def __init__(self) -> None:
        self.files: dict[str, File] = {}

    async def save(self, file: File) -> None:
        self.files[file.id] = file

    async def get_by_id(self, file_id: str) -> File | None:
        return self.files.get(file_id)


class FakeUnitOfWork:
    def __init__(self, repo: FakeFileRepository) -> None:
        self.file = repo

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def test_local_file_storage_upload_and_download(tmp_path: Path) -> None:
    repo = FakeFileRepository()
    storage = LocalFileStorage(
        uow_factory=lambda: FakeUnitOfWork(repo),
        user_id="user-1",
        storage_root=tmp_path,
    )

    upload = UploadFile(
        file=io.BytesIO(b"hello aurora"),
        filename="note.txt",
        size=12,
        headers=Headers({"content-type": "text/plain"}),
    )

    saved = asyncio.run(storage.upload_file(upload))
    file_data, stored = asyncio.run(storage.download_file(saved.id))

    assert saved.filename == "note.txt"
    assert saved.key.endswith(".txt")
    assert stored.id == saved.id
    assert file_data.read() == b"hello aurora"


def test_local_file_storage_returns_data_url_for_images(tmp_path: Path) -> None:
    repo = FakeFileRepository()
    storage = LocalFileStorage(
        uow_factory=lambda: FakeUnitOfWork(repo),
        user_id="user-1",
        storage_root=tmp_path,
    )

    upload = UploadFile(
        file=io.BytesIO(b"\x89PNG\r\n\x1a\nfake"),
        filename="chart.png",
        size=12,
        headers=Headers({"content-type": "image/png"}),
    )

    saved = asyncio.run(storage.upload_file(upload))
    url = asyncio.run(storage.get_file_url(saved))

    assert url.startswith("data:image/png;base64,")
