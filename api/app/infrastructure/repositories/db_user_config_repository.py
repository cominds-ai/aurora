from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.app_config import AppConfig, LLMConfig, AgentConfig, SearchConfig, MCPConfig, A2AConfig, \
    SandboxPreference
from app.domain.repositories.user_config_repository import UserConfigRepository
from app.infrastructure.models import UserConfigModel


class DBUserConfigRepository(UserConfigRepository):
    """数据库用户配置仓库"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    @staticmethod
    def _default_app_config() -> AppConfig:
        return AppConfig(
            llm_config=LLMConfig(),
            agent_config=AgentConfig(),
            search_config=SearchConfig(),
            mcp_config=MCPConfig(),
            a2a_config=A2AConfig(),
            sandbox_preference=SandboxPreference(),
        )

    async def load(self, user_id: str) -> Optional[AppConfig]:
        stmt = select(UserConfigModel).where(UserConfigModel.user_id == user_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return self._default_app_config()

        return AppConfig.model_validate({
            "llm_config": record.llm_config,
            "agent_config": record.agent_config,
            "search_config": record.search_config,
            "mcp_config": record.mcp_config,
            "a2a_config": record.a2a_config,
            "sandbox_preference": record.sandbox_preference,
        })

    async def save(self, user_id: str, app_config: AppConfig) -> None:
        stmt = select(UserConfigModel).where(UserConfigModel.user_id == user_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        data = app_config.model_dump(mode="json")
        if not record:
            self.db_session.add(UserConfigModel(user_id=user_id, **data))
            return

        record.llm_config = data["llm_config"]
        record.agent_config = data["agent_config"]
        record.search_config = data["search_config"]
        record.mcp_config = data["mcp_config"]
        record.a2a_config = data["a2a_config"]
        record.sandbox_preference = data["sandbox_preference"]
