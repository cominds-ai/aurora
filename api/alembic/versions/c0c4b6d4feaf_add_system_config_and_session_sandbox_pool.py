"""add system config and session sandbox pool

Revision ID: c0c4b6d4feaf
Revises: 4d6f8f8f9a10
Create Date: 2026-03-19 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c0c4b6d4feaf"
down_revision: Union[str, Sequence[str], None] = "4d6f8f8f9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("sandbox_bindings")

    op.create_table(
        "sandbox_bindings",
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("sandbox_id", sa.String(length=255), nullable=False),
        sa.Column("sandbox_label", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("cdp_url", sa.String(length=255), nullable=False),
        sa.Column("vnc_url", sa.String(length=255), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", name="pk_sandbox_bindings_session_id"),
        sa.UniqueConstraint("sandbox_id"),
    )

    op.create_table(
        "system_configs",
        sa.Column("config_key", sa.String(length=255), nullable=False),
        sa.Column(
            "sandbox_pool",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("config_key", name="pk_system_configs_config_key"),
    )


def downgrade() -> None:
    op.drop_table("system_configs")
    op.drop_table("sandbox_bindings")

    op.create_table(
        "sandbox_bindings",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("sandbox_id", sa.String(length=255), nullable=False),
        sa.Column("sandbox_label", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("cdp_url", sa.String(length=255), nullable=False),
        sa.Column("vnc_url", sa.String(length=255), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_sandbox_bindings_user_id"),
        sa.UniqueConstraint("sandbox_id"),
    )
