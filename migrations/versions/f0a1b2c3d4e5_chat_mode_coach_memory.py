"""chat_sessions.mode + coach_memory table (unified chat, A8)

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-07-04 15:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e9f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("mode", sa.String(length=24), nullable=False, server_default="general")
        )
    op.create_table(
        "coach_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("coach_memory")
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("mode")
