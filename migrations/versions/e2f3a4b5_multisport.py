"""add sport column to activities (multi-sport: bike/swim/strength)

Revision ID: e2f3a4b5
Revises: d1e2f3a4
Create Date: 2026-06-30 14:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5"
down_revision: str | None = "d1e2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("activities") as batch_op:
        batch_op.add_column(
            sa.Column("sport", sa.String(length=16), nullable=False, server_default="run")
        )
        batch_op.create_index("ix_activities_sport", ["sport"])


def downgrade() -> None:
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_index("ix_activities_sport")
        batch_op.drop_column("sport")
