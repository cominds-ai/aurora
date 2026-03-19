from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.sandbox_binding import SandboxBinding

from .base import Base


class SandboxBindingModel(Base):
    """会话级沙箱绑定ORM模型"""

    __tablename__ = "sandbox_bindings"
    __table_args__ = (PrimaryKeyConstraint("session_id", name="pk_sandbox_bindings_session_id"),)

    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    sandbox_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    sandbox_label: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    cdp_url: Mapped[str] = mapped_column(String(255), nullable=False)
    vnc_url: Mapped[str] = mapped_column(String(255), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    @classmethod
    def from_domain(cls, binding: SandboxBinding) -> "SandboxBindingModel":
        return cls(**binding.model_dump(mode="python"))

    def to_domain(self) -> SandboxBinding:
        return SandboxBinding.model_validate(self, from_attributes=True)

    def update_from_domain(self, binding: SandboxBinding) -> None:
        for field, value in binding.model_dump(mode="python").items():
            setattr(self, field, value)
