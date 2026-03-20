from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.app_config import AppConfig, AgentConfig, SearchConfig, MCPConfig, A2AConfig, \
    SandboxPreference, build_default_llm_config, ensure_builtin_llm_providers
from app.domain.repositories.user_config_repository import UserConfigRepository
from app.infrastructure.models import UserConfigModel
from core.config import get_settings


class DBUserConfigRepository(UserConfigRepository):
    """数据库用户配置仓库"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self._settings = get_settings()

    def _default_app_config(self) -> AppConfig:
        return AppConfig(
            llm_config=build_default_llm_config(
                gemini3_api_key=self._settings.aurora_official_default_gemini3_api_key,
                claude_api_key=self._settings.aurora_official_default_claude_api_key,
            ),
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

        app_config = AppConfig.model_validate({
            "llm_config": record.llm_config,
            "agent_config": record.agent_config,
            "search_config": record.search_config,
            "mcp_config": record.mcp_config,
            "a2a_config": record.a2a_config,
            "sandbox_preference": record.sandbox_preference,
        })
        app_config.llm_config = ensure_builtin_llm_providers(
            app_config.llm_config,
            gemini3_api_key=self._settings.aurora_official_default_gemini3_api_key,
            claude_api_key=self._settings.aurora_official_default_claude_api_key,
        )
        return app_config

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
