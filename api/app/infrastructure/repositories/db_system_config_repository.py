from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.system_config import SystemConfig
from app.domain.repositories.system_config_repository import SystemConfigRepository
from app.infrastructure.models import SystemConfigModel


class DBSystemConfigRepository(SystemConfigRepository):
    GLOBAL_CONFIG_KEY = "global"

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def load(self) -> SystemConfig:
        stmt = select(SystemConfigModel).where(SystemConfigModel.config_key == self.GLOBAL_CONFIG_KEY)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return SystemConfig()

        return SystemConfig.model_validate({
            "sandbox_pool": record.sandbox_pool,
        })

    async def save(self, system_config: SystemConfig) -> None:
        stmt = select(SystemConfigModel).where(SystemConfigModel.config_key == self.GLOBAL_CONFIG_KEY)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        data = system_config.model_dump(mode="json")
        if not record:
            self.db_session.add(SystemConfigModel(config_key=self.GLOBAL_CONFIG_KEY, **data))
            return

        record.sandbox_pool = data["sandbox_pool"]

