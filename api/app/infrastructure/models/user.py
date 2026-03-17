import uuid
from datetime import datetime

from sqlalchemy import DateTime, PrimaryKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.user import User

from .base import Base


class UserModel(Base):
    """用户ORM模型"""

    __tablename__ = "users"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_users_id"),)

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )

    @classmethod
    def from_domain(cls, user: User) -> "UserModel":
        return cls(**user.model_dump(mode="python"))

    def to_domain(self) -> User:
        return User.model_validate(self, from_attributes=True)

    def update_from_domain(self, user: User) -> None:
        for field, value in user.model_dump(mode="python").items():
            setattr(self, field, value)
