from typing import Protocol, Optional

from app.domain.models.app_config import AppConfig


class UserConfigRepository(Protocol):
    """用户配置仓库协议"""

    async def load(self, user_id: str) -> Optional[AppConfig]:
        ...

    async def save(self, user_id: str, app_config: AppConfig) -> None:
        ...
