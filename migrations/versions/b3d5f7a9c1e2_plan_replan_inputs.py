"""persist plan generation inputs for rolling re-plan (Fase D)

Revision ID: b3d5f7a9c1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-10 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3d5f7a9c1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("training_plans", sa.Column("days_per_week", sa.Integer(), nullable=True))
    op.add_column("training_plans", sa.Column("long_run_day", sa.Integer(), nullable=True))
    op.add_column("training_plans", sa.Column("runner_context", sa.Text(), nullable=True))
    op.add_column("training_plans", sa.Column("baseline_km", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("training_plans", "baseline_km")
    op.drop_column("training_plans", "runner_context")
    op.drop_column("training_plans", "long_run_day")
    op.drop_column("training_plans", "days_per_week")
