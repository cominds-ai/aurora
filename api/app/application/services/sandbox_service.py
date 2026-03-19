import json
import logging
import random
import shlex
from dataclasses import dataclass
from typing import Optional, List
from urllib.parse import urlparse

import httpx

from app.application.errors.exceptions import BadRequestError
from app.domain.external.sandbox import Sandbox
from app.domain.models.app_config import SandboxPreference
from app.domain.models.sandbox_binding import SandboxBinding
from app.domain.models.system_config import SystemConfig, SandboxPoolItem
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox
from app.infrastructure.external.sandbox.http_sandbox import HttpSandbox
from core.config import get_settings

logger = logging.getLogger(__name__)

SANDBOX_NOT_CONFIGURED_MESSAGE = "当前系统尚未配置可用沙箱，请联系 风后（田萧波） 添加沙箱资源"
NO_AVAILABLE_SANDBOX_MESSAGE = "当前暂无沙箱可以分配，请耐心等待"


@dataclass
class SandboxRegistryItem:
    sandbox_id: str
    label: str
    base_url: str
    cdp_url: str
    vnc_url: str


@dataclass
class SandboxPreferenceStatus:
    preferred_sandbox_host: Optional[str]
    configured: bool
    connected: bool
    needs_reconfigure: bool
    message: str


@dataclass
class SandboxPoolStatusItem:
    sandbox_id: str
    label: str
    host: str
    available: bool
    healthy: bool
    bound_user_id: Optional[str]
    bound_session_id: Optional[str]


class SandboxService:
    """用户级沙箱池服务"""

    def __init__(self, uow_factory: callable) -> None:
        self._uow_factory = uow_factory
        self._settings = get_settings()

    def _load_registry(self) -> List[SandboxRegistryItem]:
        if not self._settings.sandbox_registry_json.strip():
            return []
        raw_items = json.loads(self._settings.sandbox_registry_json)
        return [SandboxRegistryItem(**item) for item in raw_items]

    @staticmethod
    def _format_host_for_url(host: str) -> str:
        return host if ":" not in host else f"[{host}]"

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
        formatted_host = cls._format_host_for_url(host)
        return SandboxRegistryItem(
            sandbox_id=f"manual:{host}",
            label=f"DSW Sandbox ({host})",
            base_url=f"http://{formatted_host}:8080",
            cdp_url=f"http://{formatted_host}:9222",
            vnc_url=f"ws://{formatted_host}:5901",
        )

    @classmethod
    def _extract_host_from_base_url(cls, base_url: str) -> Optional[str]:
        parsed = urlparse(base_url)
        return parsed.hostname

    @classmethod
    def _build_pool_registry_item(cls, item: SandboxPoolItem) -> SandboxRegistryItem:
        formatted_host = cls._format_host_for_url(item.host)
        label = item.label or f"DSW Sandbox ({item.host})"
        return SandboxRegistryItem(
            sandbox_id=f"pool:{item.host}",
            label=label,
            base_url=f"http://{formatted_host}:8080",
            cdp_url=f"http://{formatted_host}:9222",
            vnc_url=f"ws://{formatted_host}:5901",
        )

    @classmethod
    def get_workspace_dir(cls, session_id: str) -> str:
        return f"/home/ubuntu/workspaces/{session_id}"

    @classmethod
    def get_upload_dir(cls, session_id: str) -> str:
        return f"{cls.get_workspace_dir(session_id)}/upload"

    @classmethod
    def _binding_uses_http(cls, binding: SandboxBinding) -> bool:
        return binding.sandbox_id.startswith("manual:") or binding.sandbox_id.startswith("pool:")

    @classmethod
    def _binding_matches_preference(
            cls,
            binding: SandboxBinding,
            sandbox_preference: Optional[SandboxPreference],
    ) -> bool:
        if sandbox_preference is None:
            return True

        preferred_host = cls._normalize_sandbox_host(sandbox_preference.preferred_sandbox_host)
        if not preferred_host:
            return True
        return cls._extract_host_from_base_url(binding.base_url) == preferred_host

    async def _load_system_config(self) -> SystemConfig:
        async with self._uow_factory() as uow:
            system_config = await uow.system_config.load()

        if system_config.sandbox_pool:
            return system_config

        pool_items: List[SandboxPoolItem] = []
        for item in self._load_registry():
            host = self._extract_host_from_base_url(item.base_url)
            if not host:
                continue
            pool_items.append(SandboxPoolItem(host=host, label=item.label))
        return SystemConfig(sandbox_pool=pool_items)

    async def get_system_sandbox_pool(self) -> SystemConfig:
        system_config = await self._load_system_config()
        return SystemConfig(sandbox_pool=self._deduplicate_pool(system_config.sandbox_pool))

    async def update_system_sandbox_pool(self, pool: List[SandboxPoolItem]) -> SystemConfig:
        deduped = self._deduplicate_pool(pool)
        system_config = SystemConfig(sandbox_pool=deduped)
        async with self._uow_factory() as uow:
            await uow.system_config.save(system_config)
        return system_config

    @classmethod
    def _deduplicate_pool(cls, pool: List[SandboxPoolItem]) -> List[SandboxPoolItem]:
        seen_hosts: set[str] = set()
        items: List[SandboxPoolItem] = []
        for item in pool:
            normalized = SandboxPoolItem.model_validate(item)
            if normalized.host in seen_hosts:
                continue
            seen_hosts.add(normalized.host)
            items.append(normalized)
        return items

    async def _load_pool_items(self) -> List[SandboxRegistryItem]:
        system_config = await self._load_system_config()
        if system_config.sandbox_pool:
            return [self._build_pool_registry_item(item) for item in system_config.sandbox_pool]
        if self._settings.sandbox_address:
            host = self._normalize_sandbox_host(self._settings.sandbox_address)
            if host:
                return [self._build_manual_registry_item(host)]
        return []

    async def validate_manual_host(self, host: str) -> SandboxRegistryItem:
        item = self._build_manual_registry_item(host)
        await self._ensure_manual_sandbox_alive(item)
        return item

    async def _ensure_manual_sandbox_alive(self, item: SandboxRegistryItem) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{item.base_url}/api/supervisor/status")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("沙箱鉴活失败, host=%s, error=%s", item.sandbox_id, exc)
            raise BadRequestError("当前 DSW 沙箱不可达，请确认 IP/域名有效且沙箱已启动")

        if isinstance(payload, dict) and payload.get("code") not in (0, 200):
            raise BadRequestError("当前 DSW 沙箱不可达，请确认 IP/域名有效且沙箱已启动")

    @classmethod
    def _build_binding(
            cls,
            user_id: str,
            item: SandboxRegistryItem,
            session_id: Optional[str] = None,
    ) -> SandboxBinding:
        return SandboxBinding(
            user_id=user_id,
            session_id=session_id,
            sandbox_id=item.sandbox_id,
            sandbox_label=item.label,
            base_url=item.base_url,
            cdp_url=item.cdp_url,
            vnc_url=item.vnc_url,
        )

    async def _build_preferred_item(self, host: str) -> SandboxRegistryItem:
        system_config = await self._load_system_config()
        for item in system_config.sandbox_pool:
            if item.host == host:
                return self._build_pool_registry_item(item)
        return self._build_manual_registry_item(host)

    async def _pick_available_item(
            self,
            user_id: str,
            preferred_host: Optional[str],
    ) -> SandboxRegistryItem:
        if preferred_host:
            candidates = [await self._build_preferred_item(preferred_host)]
        else:
            candidates = await self._load_pool_items()

        if not candidates:
            raise BadRequestError(SANDBOX_NOT_CONFIGURED_MESSAGE)

        healthy_candidates: List[SandboxRegistryItem] = []
        for item in candidates:
            try:
                await self._ensure_manual_sandbox_alive(item)
                healthy_candidates.append(item)
            except BadRequestError:
                logger.warning("跳过不可达沙箱: %s", item.base_url)

        if not healthy_candidates:
            raise BadRequestError(NO_AVAILABLE_SANDBOX_MESSAGE)

        available: List[SandboxRegistryItem] = []
        for item in healthy_candidates:
            async with self._uow_factory() as uow:
                occupied = await uow.sandbox_binding.get_by_sandbox_id(item.sandbox_id)
            if occupied and occupied.expired:
                await self._release_binding(occupied)
                occupied = None
            if occupied and occupied.user_id != user_id:
                continue
            if occupied and occupied.user_id == user_id:
                return item
            available.append(item)

        if not available:
            raise BadRequestError(NO_AVAILABLE_SANDBOX_MESSAGE)

        return random.choice(available)

    async def _ensure_session_workspace(self, sandbox: Sandbox, session_id: str, user_id: str) -> None:
        workspace_dir = self.get_workspace_dir(session_id)
        upload_dir = self.get_upload_dir(session_id)
        metadata = json.dumps(
            {
                "session_id": session_id,
                "user_id": user_id,
                "workspace_dir": workspace_dir,
                "upload_dir": upload_dir,
            },
            ensure_ascii=False,
            indent=2,
        )
        await sandbox.write_file(
            filepath=f"{workspace_dir}/.aurora-session.json",
            content=metadata,
            trailing_newline=True,
        )
        await sandbox.write_file(
            filepath=f"{upload_dir}/.keep",
            content="",
        )

    async def _cleanup_all_workspaces(self, binding: SandboxBinding) -> None:
        sandbox = HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)
        cleanup_session_id = f"cleanup-user-{binding.user_id}"
        try:
            result = await sandbox.exec_command(
                session_id=cleanup_session_id,
                exec_dir="/home/ubuntu",
                command="rm -rf -- /home/ubuntu/workspaces",
            )
            if result.success and result.data and result.data.get("status") == "running":
                await sandbox.wait_process(cleanup_session_id, seconds=30)
        except Exception as exc:
            logger.warning("清理用户[%s]工作目录失败: %s", binding.user_id, exc)
        finally:
            await sandbox.destroy()

    async def cleanup_session_workspace(self, user_id: str, session_id: str) -> None:
        binding = await self.get_user_binding(user_id)
        if not binding:
            return

        sandbox = HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)
        cleanup_session_id = f"cleanup-session-{session_id}"
        try:
            workspace_dir = self.get_workspace_dir(session_id)
            result = await sandbox.exec_command(
                session_id=cleanup_session_id,
                exec_dir="/home/ubuntu",
                command=f"rm -rf -- {shlex.quote(workspace_dir)}",
            )
            if result.success and result.data and result.data.get("status") == "running":
                await sandbox.wait_process(cleanup_session_id, seconds=20)
        except Exception as exc:
            logger.warning("清理会话[%s]工作目录失败: %s", session_id, exc)
        finally:
            await sandbox.destroy()

    async def _release_binding(self, binding: SandboxBinding) -> None:
        if (
                self._settings.sandbox_mode == "docker"
                and not self._settings.sandbox_address
                and not self._binding_uses_http(binding)
        ):
            sandbox = await DockerSandbox.get(binding.sandbox_id)
            if sandbox:
                await sandbox.destroy()
        elif self._binding_uses_http(binding):
            await self._cleanup_all_workspaces(binding)

        async with self._uow_factory() as uow:
            await uow.sandbox_binding.delete_by_user_id(binding.user_id)

    async def _release_if_expired(self, binding: SandboxBinding) -> None:
        if binding.expired:
            await self._release_binding(binding)

    async def get_user_binding(self, user_id: str) -> Optional[SandboxBinding]:
        async with self._uow_factory() as uow:
            binding = await uow.sandbox_binding.get_by_user_id(user_id)
        if binding and binding.expired:
            await self._release_if_expired(binding)
            return None
        return binding

    async def clear_binding_for_user(self, user_id: str) -> None:
        binding = await self.get_user_binding(user_id)
        if binding:
            await self._release_binding(binding)

    async def release_user_binding(self, user_id: str) -> None:
        await self.clear_binding_for_user(user_id)

    async def ensure_user_sandbox(
            self,
            user_id: str,
            session_id: Optional[str] = None,
            sandbox_preference: Optional[SandboxPreference] = None,
    ) -> Sandbox:
        preferred_host = self._normalize_sandbox_host(
            sandbox_preference.preferred_sandbox_host if sandbox_preference else None
        )
        binding = await self.get_user_binding(user_id)
        if binding:
            if not self._binding_matches_preference(binding, sandbox_preference):
                await self._release_binding(binding)
                binding = None
            else:
                try:
                    item = SandboxRegistryItem(
                        sandbox_id=binding.sandbox_id,
                        label=binding.sandbox_label,
                        base_url=binding.base_url,
                        cdp_url=binding.cdp_url,
                        vnc_url=binding.vnc_url,
                    )
                    await self._ensure_manual_sandbox_alive(item)
                    binding.touch(self._settings.sandbox_binding_ttl_hours)
                    binding.session_id = session_id or binding.session_id
                    async with self._uow_factory() as uow:
                        await uow.sandbox_binding.save(binding)
                    sandbox = HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)
                    if session_id:
                        await self._ensure_session_workspace(sandbox, session_id, user_id)
                    return sandbox
                except BadRequestError:
                    await self._release_binding(binding)
                    binding = None

        item = await self._pick_available_item(user_id, preferred_host)
        binding = self._build_binding(user_id=user_id, item=item, session_id=session_id)
        binding.touch(self._settings.sandbox_binding_ttl_hours)
        async with self._uow_factory() as uow:
            await uow.sandbox_binding.save(binding)
        sandbox = HttpSandbox(item.sandbox_id, item.base_url, item.cdp_url, item.vnc_url)
        if session_id:
            await self._ensure_session_workspace(sandbox, session_id, user_id)
        return sandbox

    async def get_session_sandbox(
            self,
            user_id: str,
            session_id: str,
            sandbox_preference: Optional[SandboxPreference],
    ) -> Sandbox:
        return await self.ensure_user_sandbox(
            user_id=user_id,
            session_id=session_id,
            sandbox_preference=sandbox_preference,
        )

    async def inspect_preference(
            self,
            user_id: str,
            sandbox_preference: Optional[SandboxPreference],
    ) -> SandboxPreferenceStatus:
        preferred_host = self._normalize_sandbox_host(
            sandbox_preference.preferred_sandbox_host if sandbox_preference else None
        )
        items = await self._load_pool_items()
        if not items:
            return SandboxPreferenceStatus(
                preferred_sandbox_host=preferred_host,
                configured=False,
                connected=False,
                needs_reconfigure=False,
                message=SANDBOX_NOT_CONFIGURED_MESSAGE,
            )

        if preferred_host:
            try:
                await self.validate_manual_host(preferred_host)
                return SandboxPreferenceStatus(
                    preferred_sandbox_host=preferred_host,
                    configured=True,
                    connected=True,
                    needs_reconfigure=False,
                    message="沙箱连接正常",
                )
            except BadRequestError as exc:
                return SandboxPreferenceStatus(
                    preferred_sandbox_host=preferred_host,
                    configured=True,
                    connected=False,
                    needs_reconfigure=True,
                    message=exc.msg,
                )

        return SandboxPreferenceStatus(
            preferred_sandbox_host=None,
            configured=True,
            connected=True,
            needs_reconfigure=False,
            message=f"系统沙箱池已配置，共 {len(items)} 台实例",
        )

    async def list_sandbox_pool_status(self) -> List[SandboxPoolStatusItem]:
        items = await self._load_pool_items()
        async with self._uow_factory() as uow:
            bindings = await uow.sandbox_binding.list_all()

        binding_by_sandbox_id = {}
        for binding in bindings:
            if binding.expired:
                await self._release_binding(binding)
                continue
            binding_by_sandbox_id[binding.sandbox_id] = binding

        statuses: List[SandboxPoolStatusItem] = []
        for item in items:
            binding = binding_by_sandbox_id.get(item.sandbox_id)
            healthy = True
            try:
                await self._ensure_manual_sandbox_alive(item)
            except BadRequestError:
                healthy = False
            statuses.append(
                SandboxPoolStatusItem(
                    sandbox_id=item.sandbox_id,
                    label=item.label,
                    host=self._extract_host_from_base_url(item.base_url) or "",
                    available=healthy and binding is None,
                    healthy=healthy,
                    bound_user_id=binding.user_id if binding else None,
                    bound_session_id=binding.session_id if binding else None,
                )
            )
        return statuses
