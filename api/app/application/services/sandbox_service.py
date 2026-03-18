import json
import logging
from dataclasses import dataclass
from typing import Optional, List
from urllib.parse import urlparse

from app.application.errors.exceptions import ServerRequestsError, BadRequestError
from app.domain.external.sandbox import Sandbox
from app.domain.models.app_config import SandboxPreference
from app.domain.models.sandbox_binding import SandboxBinding
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox
from app.infrastructure.external.sandbox.http_sandbox import HttpSandbox
from core.config import get_settings

logger = logging.getLogger(__name__)
SANDBOX_NOT_CONFIGURED_MESSAGE = "沙箱没有配置，沙箱不可用，请先在设置中配置 DSW 沙箱地址"


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

    @staticmethod
    def _normalize_sandbox_host(value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        raw_value = value.strip()
        if not raw_value:
            return None

        if "://" in raw_value:
            parsed = urlparse(raw_value)
            return parsed.hostname or None

        host = raw_value.split("/", 1)[0].strip()
        if not host:
            return None

        if host.startswith("[") and "]" in host:
            return host[1:host.index("]")]

        if ":" in host:
            host_candidate, port_candidate = host.rsplit(":", 1)
            if port_candidate.isdigit():
                return host_candidate

        return host

    @classmethod
    def _build_manual_registry_item(cls, host: str) -> SandboxRegistryItem:
        return SandboxRegistryItem(
            sandbox_id=f"manual:{host}",
            label=f"DSW Sandbox ({host})",
            base_url=f"http://{host}:8080",
            cdp_url=f"http://{host}:9222",
            vnc_url=f"ws://{host}:5901",
        )

    @classmethod
    def _extract_host_from_base_url(cls, base_url: str) -> Optional[str]:
        parsed = urlparse(base_url)
        return parsed.hostname

    @classmethod
    def _binding_uses_http(cls, binding: SandboxBinding) -> bool:
        return binding.sandbox_id.startswith("manual:")

    @classmethod
    def _binding_matches_preference(
            cls,
            binding: SandboxBinding,
            sandbox_preference: Optional[SandboxPreference],
    ) -> bool:
        if sandbox_preference is None:
            return True

        preferred_host = cls._normalize_sandbox_host(sandbox_preference.preferred_sandbox_host)
        if preferred_host:
            return cls._extract_host_from_base_url(binding.base_url) == preferred_host

        return True

    async def _require_configured_host(
            self,
            user_id: str,
            sandbox_preference: Optional[SandboxPreference],
    ) -> str:
        preferred_host = self._normalize_sandbox_host(
            sandbox_preference.preferred_sandbox_host if sandbox_preference else None
        )
        if preferred_host:
            return preferred_host

        binding = await self.get_binding(user_id)
        if binding:
            await self._release_binding(binding)
        raise BadRequestError(SANDBOX_NOT_CONFIGURED_MESSAGE)

    async def _release_binding(self, binding: SandboxBinding) -> None:
        if (
                self._settings.sandbox_mode == "docker"
                and not self._settings.sandbox_address
                and not self._binding_uses_http(binding)
        ):
            sandbox = await DockerSandbox.get(binding.sandbox_id)
            if sandbox:
                await sandbox.destroy()
        async with self._uow_factory() as uow:
            await uow.sandbox_binding.delete_by_user_id(binding.user_id)

    async def _release_if_expired(self, binding: SandboxBinding) -> None:
        if not binding.expired:
            return
        await self._release_binding(binding)

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

    async def assign_for_user(
            self,
            user_id: str,
            sandbox_preference: Optional[SandboxPreference] = None,
    ) -> Sandbox:
        preferred_host = await self._require_configured_host(user_id, sandbox_preference)
        binding = await self.get_binding(user_id)
        if binding:
            if not self._binding_matches_preference(binding, sandbox_preference):
                await self._release_binding(binding)
                binding = None
            else:
                binding.touch(self._settings.sandbox_binding_ttl_hours)
                async with self._uow_factory() as uow:
                    await uow.sandbox_binding.save(binding)
                return HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)

        item = self._build_manual_registry_item(preferred_host)
        async with self._uow_factory() as uow:
            occupied = await uow.sandbox_binding.get_by_sandbox_id(item.sandbox_id)
        if occupied and not occupied.expired and occupied.user_id != user_id:
            raise ServerRequestsError("指定的沙箱已被其他用户占用，请更换 VPC 内网 IP/域名或稍后重试")
        binding = SandboxBinding(
            user_id=user_id,
            sandbox_id=item.sandbox_id,
            sandbox_label=item.label,
            base_url=item.base_url,
            cdp_url=item.cdp_url,
            vnc_url=item.vnc_url,
        )
        binding.touch(self._settings.sandbox_binding_ttl_hours)
        async with self._uow_factory() as uow:
            await uow.sandbox_binding.save(binding)
        return HttpSandbox(item.sandbox_id, item.base_url, item.cdp_url, item.vnc_url)

    async def get_session_sandbox(
            self,
            user_id: str,
            sandbox_id: Optional[str],
            sandbox_preference: Optional[SandboxPreference],
    ) -> Sandbox:
        return await self.assign_for_user(user_id, sandbox_preference)
