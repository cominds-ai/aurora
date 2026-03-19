"""migrate sandbox bindings to user scope

Revision ID: 9f3b7e1d2c4a
Revises: c0c4b6d4feaf
Create Date: 2026-03-19 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3b7e1d2c4a"
down_revision: Union[str, Sequence[str], None] = "c0c4b6d4feaf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sandbox_bindings_user_scoped",
        sa.Column("session_id", sa.String(length=255), nullable=True),
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

    op.execute(
        """
        INSERT INTO sandbox_bindings_user_scoped (
            session_id,
            user_id,
            sandbox_id,
            sandbox_label,
            base_url,
            cdp_url,
            vnc_url,
            last_active_at,
            expires_at
        )
        SELECT DISTINCT ON (user_id)
            session_id,
            user_id,
            sandbox_id,
            sandbox_label,
            base_url,
            cdp_url,
            vnc_url,
            last_active_at,
            expires_at
        FROM sandbox_bindings
        ORDER BY user_id, last_active_at DESC, expires_at DESC, session_id DESC
        """
    )

    op.drop_table("sandbox_bindings")
    op.rename_table("sandbox_bindings_user_scoped", "sandbox_bindings")


def downgrade() -> None:
    op.create_table(
        "sandbox_bindings_session_scoped",
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

    op.execute(
        """
        INSERT INTO sandbox_bindings_session_scoped (
            session_id,
            user_id,
            sandbox_id,
            sandbox_label,
            base_url,
            cdp_url,
            vnc_url,
            last_active_at,
            expires_at
        )
        SELECT
            session_id,
            user_id,
            sandbox_id,
            sandbox_label,
            base_url,
            cdp_url,
            vnc_url,
            last_active_at,
            expires_at
        FROM sandbox_bindings
        WHERE session_id IS NOT NULL
        """
    )

    op.drop_table("sandbox_bindings")
    op.rename_table("sandbox_bindings_session_scoped", "sandbox_bindings")

