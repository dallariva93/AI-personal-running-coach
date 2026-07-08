"""add sample_streams and derived stream features to activities

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-07-08 14:45:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sample_streams", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("decoupling_pct", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("hr_drift_pct", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("speed_cv", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_column("speed_cv")
        batch_op.drop_column("hr_drift_pct")
        batch_op.drop_column("decoupling_pct")
        batch_op.drop_column("sample_streams")
