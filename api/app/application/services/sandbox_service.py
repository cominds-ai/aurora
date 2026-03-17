import json
import logging
from dataclasses import dataclass
from typing import Optional, List

from app.application.errors.exceptions import ServerRequestsError
from app.domain.external.sandbox import Sandbox
from app.domain.models.sandbox_binding import SandboxBinding
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox
from app.infrastructure.external.sandbox.http_sandbox import HttpSandbox
from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SandboxRegistryItem:
    sandbox_id: str
    label: str
    base_url: str
    cdp_url: str
    vnc_url: str


class SandboxService:
    """用户级沙箱绑定服务"""

    def __init__(self, uow_factory: callable) -> None:
        self._uow_factory = uow_factory
        self._settings = get_settings()

    def _load_registry(self) -> List[SandboxRegistryItem]:
        if not self._settings.sandbox_registry_json.strip():
            return []
        raw_items = json.loads(self._settings.sandbox_registry_json)
        return [SandboxRegistryItem(**item) for item in raw_items]

    async def _release_if_expired(self, binding: SandboxBinding) -> None:
        if not binding.expired:
            return
        if self._settings.sandbox_mode == "docker" and not self._settings.sandbox_address:
            sandbox = await DockerSandbox.get(binding.sandbox_id)
            if sandbox:
                await sandbox.destroy()
        async with self._uow_factory() as uow:
            await uow.sandbox_binding.delete_by_user_id(binding.user_id)

    async def get_binding(self, user_id: str) -> Optional[SandboxBinding]:
        async with self._uow_factory() as uow:
            binding = await uow.sandbox_binding.get_by_user_id(user_id)
        if binding and binding.expired:
            await self._release_if_expired(binding)
            return None
        return binding

    async def list_available_sandboxes(self) -> List[SandboxRegistryItem]:
        if self._settings.sandbox_mode == "registry":
            return self._load_registry()
        if self._settings.sandbox_address:
            return [
                SandboxRegistryItem(
                    sandbox_id="shared-sandbox",
                    label="shared-sandbox",
                    base_url=f"http://{self._settings.sandbox_address}:8080",
                    cdp_url=f"http://{self._settings.sandbox_address}:9222",
                    vnc_url=f"ws://{self._settings.sandbox_address}:5901",
                )
            ]
        return []

    async def assign_for_user(self, user_id: str, preferred_sandbox_id: Optional[str] = None) -> Sandbox:
        binding = await self.get_binding(user_id)
        if binding:
            binding.touch(self._settings.sandbox_binding_ttl_hours)
            async with self._uow_factory() as uow:
                await uow.sandbox_binding.save(binding)
            if self._settings.sandbox_mode == "registry" or self._settings.sandbox_address:
                return HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)
            sandbox = await DockerSandbox.get(binding.sandbox_id)
            if sandbox:
                return sandbox
            async with self._uow_factory() as uow:
                await uow.sandbox_binding.delete_by_user_id(user_id)

        if self._settings.sandbox_mode == "registry":
            sandboxes = await self.list_available_sandboxes()
            if preferred_sandbox_id:
                sandboxes = [item for item in sandboxes if item.sandbox_id == preferred_sandbox_id]
            for item in sandboxes:
                async with self._uow_factory() as uow:
                    occupied = await uow.sandbox_binding.get_by_sandbox_id(item.sandbox_id)
                if occupied and not occupied.expired:
                    continue
                new_binding = SandboxBinding(
                    user_id=user_id,
                    sandbox_id=item.sandbox_id,
                    sandbox_label=item.label,
                    base_url=item.base_url,
                    cdp_url=item.cdp_url,
                    vnc_url=item.vnc_url,
                )
                new_binding.touch(self._settings.sandbox_binding_ttl_hours)
                async with self._uow_factory() as uow:
                    await uow.sandbox_binding.save(new_binding)
                return HttpSandbox(item.sandbox_id, item.base_url, item.cdp_url, item.vnc_url)
            raise ServerRequestsError("没有可分配的沙箱，请更换沙箱或稍后重试")

        if self._settings.sandbox_address:
            sandbox = await DockerSandbox.create()
            binding = SandboxBinding(
                user_id=user_id,
                sandbox_id=sandbox.id,
                sandbox_label=sandbox.id,
                base_url=f"http://{self._settings.sandbox_address}:8080",
                cdp_url=f"http://{self._settings.sandbox_address}:9222",
                vnc_url=f"ws://{self._settings.sandbox_address}:5901",
            )
        else:
            sandbox = await DockerSandbox.create()
            binding = SandboxBinding(
                user_id=user_id,
                sandbox_id=sandbox.id,
                sandbox_label=sandbox.id,
                base_url=f"http://{sandbox._ip}:8080",
                cdp_url=sandbox.cdp_url,
                vnc_url=sandbox.vnc_url,
            )
        binding.touch(self._settings.sandbox_binding_ttl_hours)
        async with self._uow_factory() as uow:
            await uow.sandbox_binding.save(binding)
        return sandbox

    async def get_session_sandbox(self, user_id: str, sandbox_id: Optional[str], preferred_sandbox_id: Optional[str]) -> Sandbox:
        if sandbox_id:
            if self._settings.sandbox_mode == "docker" and not self._settings.sandbox_address:
                sandbox = await DockerSandbox.get(sandbox_id)
                if sandbox:
                    return sandbox
            else:
                return await self.assign_for_user(user_id, preferred_sandbox_id)
        return await self.assign_for_user(user_id, preferred_sandbox_id)
