from typing import Optional, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.sandbox_binding import SandboxBinding
from app.domain.repositories.sandbox_binding_repository import SandboxBindingRepository
from app.infrastructure.models import SandboxBindingModel


class DBSandboxBindingRepository(SandboxBindingRepository):
    """数据库沙箱绑定仓库"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def save(self, binding: SandboxBinding) -> None:
        stmt = select(SandboxBindingModel).where(SandboxBindingModel.user_id == binding.user_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            self.db_session.add(SandboxBindingModel.from_domain(binding))
            return
        record.update_from_domain(binding)

    async def get_by_user_id(self, user_id: str) -> Optional[SandboxBinding]:
        stmt = select(SandboxBindingModel).where(SandboxBindingModel.user_id == user_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record else None

    async def get_by_session_id(self, session_id: str) -> Optional[SandboxBinding]:
        stmt = select(SandboxBindingModel).where(SandboxBindingModel.session_id == session_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record else None

    async def list_by_user_id(self, user_id: str) -> List[SandboxBinding]:
        stmt = select(SandboxBindingModel).where(SandboxBindingModel.user_id == user_id)
        result = await self.db_session.execute(stmt)
        return [record.to_domain() for record in result.scalars().all()]

    async def get_by_sandbox_id(self, sandbox_id: str) -> Optional[SandboxBinding]:
        stmt = select(SandboxBindingModel).where(SandboxBindingModel.sandbox_id == sandbox_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.to_domain() if record else None

    async def list_all(self) -> List[SandboxBinding]:
        stmt = select(SandboxBindingModel)
        result = await self.db_session.execute(stmt)
        return [record.to_domain() for record in result.scalars().all()]

    async def delete_by_session_id(self, session_id: str) -> None:
        await self.db_session.execute(
            delete(SandboxBindingModel).where(SandboxBindingModel.session_id == session_id)
        )

    async def delete_by_user_id(self, user_id: str) -> None:
        await self.db_session.execute(
            delete(SandboxBindingModel).where(SandboxBindingModel.user_id == user_id)
        )
