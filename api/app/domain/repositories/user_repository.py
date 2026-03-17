from typing import Protocol, Optional

from app.domain.models.user import User


class UserRepository(Protocol):
    """用户仓库协议"""

    async def save(self, user: User) -> None:
        ...

    async def get_by_id(self, user_id: str) -> Optional[User]:
        ...

    async def get_by_username(self, username: str) -> Optional[User]:
        ...
