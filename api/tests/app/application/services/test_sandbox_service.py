import asyncio
from dataclasses import dataclass

import pytest

from app.application.errors.exceptions import BadRequestError
from app.application.services.sandbox_service import SandboxService
from app.domain.models.app_config import SandboxPreference
from app.domain.models.sandbox_binding import SandboxBinding
from app.infrastructure.external.sandbox.http_sandbox import HttpSandbox


class FakeSandboxBindingRepository:
    def __init__(self) -> None:
        self._bindings_by_user_id: dict[str, SandboxBinding] = {}

    async def save(self, binding: SandboxBinding) -> None:
        existing = await self.get_by_user_id(binding.user_id)
        if existing and existing.sandbox_id != binding.sandbox_id:
            self._bindings_by_user_id.pop(binding.user_id, None)
        self._bindings_by_user_id[binding.user_id] = binding

    async def get_by_user_id(self, user_id: str) -> SandboxBinding | None:
        return self._bindings_by_user_id.get(user_id)

    async def get_by_sandbox_id(self, sandbox_id: str) -> SandboxBinding | None:
        for binding in self._bindings_by_user_id.values():
            if binding.sandbox_id == sandbox_id:
                return binding
        return None

    async def list_all(self) -> list[SandboxBinding]:
        return list(self._bindings_by_user_id.values())

    async def delete_by_user_id(self, user_id: str) -> None:
        self._bindings_by_user_id.pop(user_id, None)


class FakeUnitOfWork:
    def __init__(self, sandbox_binding_repo: FakeSandboxBindingRepository) -> None:
        self.sandbox_binding = sandbox_binding_repo

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


@dataclass
class FakeSettings:
    sandbox_mode: str = "docker"
    sandbox_address: str | None = None
    sandbox_binding_ttl_hours: int = 72
    sandbox_registry_json: str = "[]"


async def _noop_alive_check(self, item) -> None:
    return None


def test_assign_for_user_uses_preferred_sandbox_host(monkeypatch):
    repo = FakeSandboxBindingRepository()
    settings = FakeSettings()

    monkeypatch.setattr(
        "app.application.services.sandbox_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(SandboxService, "_ensure_manual_sandbox_alive", _noop_alive_check)

    service = SandboxService(uow_factory=lambda: FakeUnitOfWork(repo))

    sandbox = asyncio.run(
        service.assign_for_user(
            "user-1",
            SandboxPreference(preferred_sandbox_host="10.1.2.3"),
        )
    )

    binding = asyncio.run(repo.get_by_user_id("user-1"))
    assert isinstance(sandbox, HttpSandbox)
    assert binding is not None
    assert binding.sandbox_id == "manual:10.1.2.3"
    assert binding.base_url == "http://10.1.2.3:8080"
    assert binding.cdp_url == "http://10.1.2.3:9222"
    assert binding.vnc_url == "ws://10.1.2.3:5901"


def test_assign_for_user_switches_binding_when_preferred_sandbox_host_changes(monkeypatch):
    repo = FakeSandboxBindingRepository()
    settings = FakeSettings()

    monkeypatch.setattr(
        "app.application.services.sandbox_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(SandboxService, "_ensure_manual_sandbox_alive", _noop_alive_check)

    service = SandboxService(uow_factory=lambda: FakeUnitOfWork(repo))

    asyncio.run(
        service.assign_for_user(
            "user-1",
            SandboxPreference(preferred_sandbox_host="http://10.1.2.3:8080"),
        )
    )
    sandbox = asyncio.run(
        service.assign_for_user(
            "user-1",
            SandboxPreference(preferred_sandbox_host="dsw-sandbox.internal"),
        )
    )

    binding = asyncio.run(repo.get_by_user_id("user-1"))
    assert isinstance(sandbox, HttpSandbox)
    assert binding is not None
    assert binding.sandbox_id == "manual:dsw-sandbox.internal"
    assert binding.base_url == "http://dsw-sandbox.internal:8080"


def test_assign_for_user_raises_when_sandbox_host_not_configured(monkeypatch):
    repo = FakeSandboxBindingRepository()
    settings = FakeSettings()

    monkeypatch.setattr(
        "app.application.services.sandbox_service.get_settings",
        lambda: settings,
    )

    service = SandboxService(uow_factory=lambda: FakeUnitOfWork(repo))

    with pytest.raises(BadRequestError) as exc_info:
        asyncio.run(
            service.assign_for_user(
                "user-1",
                SandboxPreference(),
            )
        )

    assert "沙箱没有配置" in exc_info.value.msg


def test_assign_for_user_rejects_occupied_sandbox(monkeypatch):
    repo = FakeSandboxBindingRepository()
    settings = FakeSettings()

    monkeypatch.setattr(
        "app.application.services.sandbox_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(SandboxService, "_ensure_manual_sandbox_alive", _noop_alive_check)

    service = SandboxService(uow_factory=lambda: FakeUnitOfWork(repo))

    asyncio.run(
        service.assign_for_user(
            "user-1",
            SandboxPreference(preferred_sandbox_host="10.1.2.3"),
        )
    )

    with pytest.raises(BadRequestError) as exc_info:
        asyncio.run(
            service.assign_for_user(
                "user-2",
                SandboxPreference(preferred_sandbox_host="10.1.2.3"),
            )
        )

    assert "已被其他用户占用" in exc_info.value.msg


def test_inspect_preference_marks_invalid_and_releases_binding(monkeypatch):
    repo = FakeSandboxBindingRepository()
    settings = FakeSettings()

    monkeypatch.setattr(
        "app.application.services.sandbox_service.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(SandboxService, "_ensure_manual_sandbox_alive", _noop_alive_check)

    service = SandboxService(uow_factory=lambda: FakeUnitOfWork(repo))

    asyncio.run(
        service.assign_for_user(
            "user-1",
            SandboxPreference(preferred_sandbox_host="10.1.2.3"),
        )
    )

    async def _raise_alive_check(self, item) -> None:
        raise BadRequestError("当前 DSW 沙箱不可达，请确认 IP/域名有效且沙箱已启动")

    monkeypatch.setattr(SandboxService, "_ensure_manual_sandbox_alive", _raise_alive_check)

    status = asyncio.run(
        service.inspect_preference(
            "user-1",
            SandboxPreference(preferred_sandbox_host="10.1.2.3"),
        )
    )

    binding = asyncio.run(repo.get_by_user_id("user-1"))
    assert status.connected is False
    assert status.needs_reconfigure is True
    assert "不可达" in status.message
    assert binding is None
