"""add health_connect_id to activities (Health Connect MVP, A2)

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-07-04 09:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("activities") as batch_op:
        batch_op.add_column(sa.Column("health_connect_id", sa.String(length=96), nullable=True))
        batch_op.create_index(
            "ix_activities_health_connect_id", ["health_connect_id"], unique=False
        )
        batch_op.create_unique_constraint(
            "uq_activity_health_connect_id", ["health_connect_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_constraint("uq_activity_health_connect_id", type_="unique")
        batch_op.drop_index("ix_activities_health_connect_id")
        batch_op.drop_column("health_connect_id")
