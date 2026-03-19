from typing import Protocol

from app.domain.models.system_config import SystemConfig


class SystemConfigRepository(Protocol):
    async def load(self) -> SystemConfig:
        ...

    async def save(self, system_config: SystemConfig) -> None:
        ...

