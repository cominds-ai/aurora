"""add multi-user and sandbox bindings

Revision ID: 4d6f8f8f9a10
Revises: 0e0d242438bc
Create Date: 2025-09-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "4d6f8f8f9a10"
down_revision: Union[str, Sequence[str], None] = "0e0d242438bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users_id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "user_configs",
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("llm_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("agent_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("search_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("mcp_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("a2a_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("sandbox_preference", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_configs_user_id"),
    )
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

    op.add_column("sessions", sa.Column("user_id", sa.String(length=255), server_default="", nullable=False))
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.add_column("files", sa.Column("user_id", sa.String(length=255), server_default="", nullable=False))
    op.create_index("ix_files_user_id", "files", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_files_user_id", table_name="files")
    op.drop_column("files", "user_id")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_column("sessions", "user_id")
    op.drop_table("sandbox_bindings")
    op.drop_table("user_configs")
    op.drop_table("users")
