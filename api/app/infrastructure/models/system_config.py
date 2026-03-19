from sqlalchemy import PrimaryKeyConstraint, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemConfigModel(Base):
    __tablename__ = "system_configs"
    __table_args__ = (PrimaryKeyConstraint("config_key", name="pk_system_configs_config_key"),)

    config_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
    )
    sandbox_pool: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

