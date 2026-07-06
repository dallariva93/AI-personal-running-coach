"""add live_id to activities (live GPS runs, G1 milestone M1)

Revision ID: 0a1b2c3d4e5f
Revises: f0a1b2c3d4e5
Create Date: 2026-07-04 18:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("activities") as batch_op:
        batch_op.add_column(sa.Column("live_id", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_activities_live_id", ["live_id"], unique=False)
        batch_op.create_unique_constraint("uq_activity_live_id", ["live_id"])


def downgrade() -> None:
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_constraint("uq_activity_live_id", type_="unique")
        batch_op.drop_index("ix_activities_live_id")
        batch_op.drop_column("live_id")
