import io
from typing import Optional, BinaryIO

import httpx

from app.domain.external.browser import Browser
from app.domain.external.sandbox import Sandbox
from app.domain.models.tool_result import ToolResult
from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser


class HttpSandbox(Sandbox):
    """基于HTTP端点的远程沙箱"""

    def __init__(self, sandbox_id: str, base_url: str, cdp_url: str, vnc_url: str) -> None:
        self._id = sandbox_id
        self._base_url = base_url.rstrip("/")
        self._cdp_url = cdp_url
        self._vnc_url = vnc_url
        self.client = httpx.AsyncClient(timeout=600)

    @property
    def id(self) -> str:
        return self._id

    @property
    def cdp_url(self) -> str:
        return self._cdp_url

    @property
    def vnc_url(self) -> str:
        return self._vnc_url

    async def get_browser(self) -> Browser:
        return PlaywrightBrowser(self.cdp_url)

    async def ensure_sandbox(self) -> None:
        response = await self.client.get(f"{self._base_url}/api/supervisor/status")
        response.raise_for_status()

    async def destroy(self) -> bool:
        await self.client.aclose()
        return True

    async def read_file(self, filepath: str, start_line: Optional[int] = None, end_line: Optional[int] = None,
                        sudo: bool = False, max_length: int = 10000) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/file/read-file",
            json={"filepath": filepath, "start_line": start_line, "end_line": end_line, "sudo": sudo,
                  "max_length": max_length},
        )
        return ToolResult.from_sandbox(**response.json())

    async def write_file(self, filepath: str, content: str, append: bool = False, leading_newline: bool = False,
                         trailing_newline: bool = False, sudo: bool = False) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/file/write-file",
            json={"filepath": filepath, "content": content, "append": append, "leading_newline": leading_newline,
                  "trailing_newline": trailing_newline, "sudo": sudo},
        )
        return ToolResult.from_sandbox(**response.json())

    async def replace_in_file(self, filepath: str, old_str: str, new_str: str, sudo: bool = False) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/file/replace-in-file",
            json={"filepath": filepath, "old_str": old_str, "new_str": new_str, "sudo": sudo},
        )
        return ToolResult.from_sandbox(**response.json())

    async def search_in_file(self, filepath: str, regex: str, sudo: bool = False) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/file/search-in-file",
            json={"filepath": filepath, "regex": regex, "sudo": sudo},
        )
        return ToolResult.from_sandbox(**response.json())

    async def find_files(self, dir_path: str, glob_pattern: str) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/file/find-files",
            json={"dir_path": dir_path, "glob_pattern": glob_pattern},
        )
        return ToolResult.from_sandbox(**response.json())

    async def check_file_exists(self, filepath: str) -> ToolResult:
        response = await self.client.post(f"{self._base_url}/api/file/check-file-exists", json={"filepath": filepath})
        return ToolResult.from_sandbox(**response.json())

    async def delete_file(self, filepath: str) -> ToolResult:
        response = await self.client.post(f"{self._base_url}/api/file/delete-file", json={"filepath": filepath})
        return ToolResult.from_sandbox(**response.json())

    async def list_files(self, dir_path: str) -> ToolResult:
        response = await self.client.post(f"{self._base_url}/api/file/list-files", json={"dir_path": dir_path})
        return ToolResult.from_sandbox(**response.json())

    async def upload_file(self, file_data: BinaryIO, filepath: str, filename: str = None) -> ToolResult:
        files = {"file": (filename or filepath.split("/")[-1], file_data)}
        response = await self.client.post(
            f"{self._base_url}/api/file/upload-file",
            data={"filepath": filepath},
            files=files,
        )
        return ToolResult.from_sandbox(**response.json())

    async def download_file(self, filepath: str) -> BinaryIO:
        response = await self.client.get(f"{self._base_url}/api/file/download-file", params={"filepath": filepath})
        response.raise_for_status()
        return io.BytesIO(response.content)

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/shell/exec-command",
            json={"session_id": session_id, "exec_dir": exec_dir, "command": command},
        )
        return ToolResult.from_sandbox(**response.json())

    async def read_shell_output(self, session_id: str, console: bool = False) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/shell/read-shell-output",
            json={"session_id": session_id, "console": console},
        )
        return ToolResult.from_sandbox(**response.json())

    async def wait_process(self, session_id: str, seconds: Optional[int] = None) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/shell/wait-process",
            json={"session_id": session_id, "seconds": seconds},
        )
        return ToolResult.from_sandbox(**response.json())

    async def write_shell_input(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/shell/write-shell-input",
            json={"session_id": session_id, "input_text": input_text, "press_enter": press_enter},
        )
        return ToolResult.from_sandbox(**response.json())

    async def kill_process(self, session_id: str) -> ToolResult:
        response = await self.client.post(
            f"{self._base_url}/api/shell/kill-process",
            json={"session_id": session_id},
        )
        return ToolResult.from_sandbox(**response.json())

    @classmethod
    async def create(cls):
        raise NotImplementedError

    @classmethod
    async def get(cls, id: str):
        raise NotImplementedError
