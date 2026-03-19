import asyncio
import json
import logging
import random
import shlex
import time
from dataclasses import dataclass
from typing import Optional, List, Callable, Awaitable
from urllib.parse import urlparse

import httpx

from app.application.errors.exceptions import BadRequestError
from app.domain.external.sandbox import Sandbox
from app.domain.models.app_config import SandboxPreference
from app.domain.models.sandbox_binding import SandboxBinding
from app.domain.models.session import SessionStatus
from app.domain.models.system_config import SystemConfig, SandboxPoolItem
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox
from app.infrastructure.external.sandbox.http_sandbox import HttpSandbox
from app.infrastructure.storage.redis import get_redis
from core.config import get_settings

logger = logging.getLogger(__name__)
SANDBOX_NOT_CONFIGURED_MESSAGE = "系统尚未配置可用的沙箱池，请联系管理员维护 DSW sandbox IP 池"


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


@dataclass
class SandboxQueueStatus:
    session_id: str
    user_id: str
    position: int
    size: int
    preferred_host: Optional[str]


@dataclass
class SandboxQueueEntry:
    session_id: str
    user_id: str
    preferred_host: Optional[str]


class SandboxService:
    """会话级沙箱池服务"""
    ACQUIRE_TIMEOUT_SECONDS = 240
    ACQUIRE_POLL_INTERVAL_SECONDS = 3
    QUEUE_KEY = "sandbox:wait_queue"
    QUEUE_META_KEY = "sandbox:wait_queue:meta"
    QUEUE_LEASE_PREFIX = "sandbox:wait_queue:lease:"
    QUEUE_LEASE_TTL_SECONDS = ACQUIRE_TIMEOUT_SECONDS + 30

    def __init__(self, uow_factory: callable) -> None:
        self._uow_factory = uow_factory
        self._settings = get_settings()

    @property
    def _redis(self):
        return get_redis().client

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
    def _binding_uses_http(cls, binding: SandboxBinding) -> bool:
        return binding.sandbox_id.startswith("manual:") or binding.sandbox_id.startswith("pool:")

    @classmethod
    def get_workspace_dir(cls, session_id: str) -> str:
        return f"/home/ubuntu/workspaces/{session_id}"

    @classmethod
    def get_upload_dir(cls, session_id: str) -> str:
        return f"{cls.get_workspace_dir(session_id)}/upload"

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
        deduped = self._deduplicate_pool(system_config.sandbox_pool)
        return SystemConfig(sandbox_pool=deduped)

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
            await self._cleanup_session_workspace(binding)
        async with self._uow_factory() as uow:
            await uow.sandbox_binding.delete_by_session_id(binding.session_id)

    async def clear_binding_for_user(self, user_id: str) -> None:
        async with self._uow_factory() as uow:
            bindings = await uow.sandbox_binding.list_by_user_id(user_id)
        for binding in bindings:
            await self._release_binding(binding)

    async def release_session_binding(self, session_id: str) -> None:
        await self._remove_waiter(session_id)
        binding = await self.get_binding(session_id)
        if binding:
            await self._release_binding(binding)

    async def _release_if_expired(self, binding: SandboxBinding) -> None:
        if not binding.expired:
            return
        await self._release_binding(binding)

    async def get_binding(self, session_id: str) -> Optional[SandboxBinding]:
        async with self._uow_factory() as uow:
            binding = await uow.sandbox_binding.get_by_session_id(session_id)
        if binding and binding.expired:
            await self._release_if_expired(binding)
            return None
        return binding

    async def list_available_sandboxes(self) -> List[SandboxRegistryItem]:
        return await self._load_pool_items()

    @classmethod
    def _queue_lease_key(cls, session_id: str) -> str:
        return f"{cls.QUEUE_LEASE_PREFIX}{session_id}"

    @staticmethod
    def _serialize_queue_entry(entry: SandboxQueueEntry) -> str:
        return json.dumps(
            {
                "session_id": entry.session_id,
                "user_id": entry.user_id,
                "preferred_host": entry.preferred_host,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_queue_entry(session_id: str, raw: Optional[str]) -> SandboxQueueEntry:
        payload = json.loads(raw) if raw else {}
        return SandboxQueueEntry(
            session_id=session_id,
            user_id=str(payload.get("user_id", "")),
            preferred_host=payload.get("preferred_host"),
        )

    async def _refresh_waiter_lease(self, session_id: str) -> None:
        await self._redis.set(self._queue_lease_key(session_id), "1", ex=self.QUEUE_LEASE_TTL_SECONDS)

    async def _prune_stale_waiters(self) -> None:
        session_ids = await self._redis.zrange(self.QUEUE_KEY, 0, -1)
        if not session_ids:
            return

        stale_session_ids: List[str] = []
        for queued_session_id in session_ids:
            if not await self._redis.exists(self._queue_lease_key(queued_session_id)):
                stale_session_ids.append(queued_session_id)

        if not stale_session_ids:
            return

        await self._redis.zrem(self.QUEUE_KEY, *stale_session_ids)
        await self._redis.hdel(self.QUEUE_META_KEY, *stale_session_ids)

    async def _build_queue_status(self, session_id: str) -> Optional[SandboxQueueStatus]:
        await self._prune_stale_waiters()
        rank = await self._redis.zrank(self.QUEUE_KEY, session_id)
        if rank is None:
            return None

        size = await self._redis.zcard(self.QUEUE_KEY)
        raw_meta = await self._redis.hget(self.QUEUE_META_KEY, session_id)
        entry = self._deserialize_queue_entry(session_id, raw_meta)
        return SandboxQueueStatus(
            session_id=session_id,
            user_id=entry.user_id,
            position=int(rank) + 1,
            size=int(size),
            preferred_host=entry.preferred_host,
        )

    async def _enqueue_waiter(
            self,
            session_id: str,
            user_id: str,
            preferred_host: Optional[str],
    ) -> SandboxQueueStatus:
        await self._prune_stale_waiters()
        entry = SandboxQueueEntry(
            session_id=session_id,
            user_id=user_id,
            preferred_host=preferred_host,
        )
        await self._refresh_waiter_lease(session_id)
        await self._redis.hset(self.QUEUE_META_KEY, session_id, self._serialize_queue_entry(entry))
        await self._redis.zadd(
            self.QUEUE_KEY,
            {session_id: float(time.time_ns())},
            nx=True,
        )
        status = await self._build_queue_status(session_id)
        if status is None:
            raise RuntimeError("沙箱排队状态异常")
        return status

    async def _queue_has_other_waiters(self, session_id: str) -> bool:
        await self._prune_stale_waiters()
        size = int(await self._redis.zcard(self.QUEUE_KEY))
        if size == 0:
            return False
        rank = await self._redis.zrank(self.QUEUE_KEY, session_id)
        return rank is None and size > 0

    async def _remove_waiter(self, session_id: str) -> None:
        await self._redis.zrem(self.QUEUE_KEY, session_id)
        await self._redis.hdel(self.QUEUE_META_KEY, session_id)
        await self._redis.delete(self._queue_lease_key(session_id))

    async def get_queue_status(self, session_id: str) -> Optional[SandboxQueueStatus]:
        return await self._build_queue_status(session_id)

    async def list_queue_statuses(self) -> dict[str, SandboxQueueStatus]:
        await self._prune_stale_waiters()
        session_ids = await self._redis.zrange(self.QUEUE_KEY, 0, -1)
        if not session_ids:
            return {}

        raw_entries = await self._redis.hmget(self.QUEUE_META_KEY, session_ids)
        size = len(session_ids)
        statuses: dict[str, SandboxQueueStatus] = {}
        for index, session_id in enumerate(session_ids):
            entry = self._deserialize_queue_entry(session_id, raw_entries[index] if raw_entries else None)
            statuses[session_id] = SandboxQueueStatus(
                session_id=session_id,
                user_id=entry.user_id,
                position=index + 1,
                size=size,
                preferred_host=entry.preferred_host,
            )
        return statuses

    @staticmethod
    async def _emit_queue_update(
            callback: Optional[Callable[[SandboxQueueStatus], Awaitable[None]]],
            status: SandboxQueueStatus,
    ) -> None:
        if callback is None:
            return
        await callback(status)

    async def _ensure_session_request_active(self, session_id: str) -> None:
        async with self._uow_factory() as uow:
            session = await uow.session.get_by_id(session_id)
        if session is None or session.status == SessionStatus.COMPLETED:
            raise BadRequestError("当前任务已停止")

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

    async def _ensure_manual_sandbox_available(self, user_id: str, item: SandboxRegistryItem) -> None:
        async with self._uow_factory() as uow:
            occupied = await uow.sandbox_binding.get_by_sandbox_id(item.sandbox_id)
        if occupied and occupied.expired:
            await self._release_binding(occupied)
            occupied = None
        if occupied and occupied.user_id != user_id:
            raise BadRequestError("指定的沙箱已被其他用户占用，请更换 DSW 沙箱 IP/域名或稍后重试")

    @classmethod
    def _build_binding(cls, session_id: str, user_id: str, item: SandboxRegistryItem) -> SandboxBinding:
        return SandboxBinding(
            session_id=session_id,
            user_id=user_id,
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
            session_id: str,
            user_id: str,
            preferred_host: Optional[str],
    ) -> Optional[SandboxRegistryItem]:
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
            raise BadRequestError("当前没有可用的沙箱实例，请联系管理员检查沙箱池配置")

        available: List[SandboxRegistryItem] = []
        for item in healthy_candidates:
            async with self._uow_factory() as uow:
                occupied = await uow.sandbox_binding.get_by_sandbox_id(item.sandbox_id)
            if occupied and occupied.expired:
                await self._release_binding(occupied)
                occupied = None
            if occupied:
                if occupied.session_id == session_id:
                    return item
                continue
            available.append(item)

        if not available:
            return None
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

    async def _cleanup_session_workspace(self, binding: SandboxBinding) -> None:
        sandbox = HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)
        cleanup_session_id = f"cleanup-{binding.session_id}"
        try:
            workspace_dir = self.get_workspace_dir(binding.session_id)
            result = await sandbox.exec_command(
                session_id=cleanup_session_id,
                exec_dir="/home/ubuntu",
                command=f"rm -rf -- {shlex.quote(workspace_dir)}",
            )
            if result.success and result.data and result.data.get("status") == "running":
                await sandbox.wait_process(cleanup_session_id, seconds=20)
        except Exception as exc:
            logger.warning("清理会话工作目录失败, session=%s, error=%s", binding.session_id, exc)
        finally:
            await sandbox.destroy()

    async def inspect_preference(
            self,
            user_id: str,
            sandbox_preference: Optional[SandboxPreference],
    ) -> SandboxPreferenceStatus:
        preferred_host = self._normalize_sandbox_host(
            sandbox_preference.preferred_sandbox_host if sandbox_preference else None
        )
        if not preferred_host:
            items = await self._load_pool_items()
            if items:
                return SandboxPreferenceStatus(
                    preferred_sandbox_host=None,
                    configured=True,
                    connected=True,
                    needs_reconfigure=False,
                    message=f"系统沙箱池已配置，共 {len(items)} 台实例",
                )
            return SandboxPreferenceStatus(
                preferred_sandbox_host=None,
                configured=False,
                connected=False,
                needs_reconfigure=False,
                message=SANDBOX_NOT_CONFIGURED_MESSAGE,
            )

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

    async def acquire_for_session(
            self,
            user_id: str,
            session_id: str,
            sandbox_preference: Optional[SandboxPreference] = None,
            on_queue_update: Optional[Callable[[SandboxQueueStatus], Awaitable[None]]] = None,
    ) -> Sandbox:
        preferred_host = self._normalize_sandbox_host(
            sandbox_preference.preferred_sandbox_host if sandbox_preference else None
        )
        binding = await self.get_binding(session_id)
        if binding:
            if not self._binding_matches_preference(binding, sandbox_preference):
                await self._release_binding(binding)
                binding = None
            else:
                try:
                    await self._ensure_manual_sandbox_alive(
                        SandboxRegistryItem(
                            sandbox_id=binding.sandbox_id,
                            label=binding.sandbox_label,
                            base_url=binding.base_url,
                            cdp_url=binding.cdp_url,
                            vnc_url=binding.vnc_url,
                        )
                    )
                    binding.touch(self._settings.sandbox_binding_ttl_hours)
                    async with self._uow_factory() as uow:
                        await uow.sandbox_binding.save(binding)
                    return HttpSandbox(binding.sandbox_id, binding.base_url, binding.cdp_url, binding.vnc_url)
                except BadRequestError:
                    await self._release_binding(binding)
                    binding = None

        deadline = asyncio.get_event_loop().time() + self.ACQUIRE_TIMEOUT_SECONDS
        last_reported_queue: Optional[tuple[int, int]] = None
        try:
            while True:
                await self._ensure_session_request_active(session_id)
                queue_status = await self.get_queue_status(session_id)
                if queue_status is None and await self._queue_has_other_waiters(session_id):
                    queue_status = await self._enqueue_waiter(session_id, user_id, preferred_host)
                elif queue_status is not None:
                    await self._refresh_waiter_lease(session_id)

                if queue_status is not None and queue_status.position > 1:
                    queue_key = (queue_status.position, queue_status.size)
                    if queue_key != last_reported_queue:
                        await self._emit_queue_update(on_queue_update, queue_status)
                        last_reported_queue = queue_key
                    if asyncio.get_event_loop().time() >= deadline:
                        raise BadRequestError("当前沙箱池已满，请稍后重试")
                    await asyncio.sleep(self.ACQUIRE_POLL_INTERVAL_SECONDS)
                    continue

                item = await self._pick_available_item(session_id, user_id, preferred_host)
                if item is not None:
                    break

                current_queue_status = await self._enqueue_waiter(session_id, user_id, preferred_host)
                queue_key = (current_queue_status.position, current_queue_status.size)
                if queue_key != last_reported_queue:
                    await self._emit_queue_update(on_queue_update, current_queue_status)
                    last_reported_queue = queue_key
                if asyncio.get_event_loop().time() >= deadline:
                    raise BadRequestError("当前沙箱池已满，请稍后重试")
                await asyncio.sleep(self.ACQUIRE_POLL_INTERVAL_SECONDS)

            await self._remove_waiter(session_id)
            binding = self._build_binding(session_id, user_id, item)
            binding.touch(self._settings.sandbox_binding_ttl_hours)
            async with self._uow_factory() as uow:
                await uow.sandbox_binding.save(binding)
            sandbox = HttpSandbox(item.sandbox_id, item.base_url, item.cdp_url, item.vnc_url)
            await self._ensure_session_workspace(sandbox, session_id, user_id)
            return sandbox
        finally:
            await self._remove_waiter(session_id)

    async def get_session_sandbox(
            self,
            user_id: str,
            session_id: str,
            sandbox_preference: Optional[SandboxPreference],
            on_queue_update: Optional[Callable[[SandboxQueueStatus], Awaitable[None]]] = None,
    ) -> Sandbox:
        return await self.acquire_for_session(user_id, session_id, sandbox_preference, on_queue_update)

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
