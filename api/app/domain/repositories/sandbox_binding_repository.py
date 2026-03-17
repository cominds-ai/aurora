from typing import Protocol, Optional, List

from app.domain.models.sandbox_binding import SandboxBinding


class SandboxBindingRepository(Protocol):
    """沙箱绑定仓库协议"""

    async def save(self, binding: SandboxBinding) -> None:
        ...

    async def get_by_user_id(self, user_id: str) -> Optional[SandboxBinding]:
        ...

    async def get_by_sandbox_id(self, sandbox_id: str) -> Optional[SandboxBinding]:
        ...

    async def list_all(self) -> List[SandboxBinding]:
        ...

    async def delete_by_user_id(self, user_id: str) -> None:
        ...
