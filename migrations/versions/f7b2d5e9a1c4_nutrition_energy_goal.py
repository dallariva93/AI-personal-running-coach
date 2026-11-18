"""nutrition: the day's calorie target

Intake on its own says very little: 1900 kcal is generous or a deep hole
depending on what the day required. The deficit is the whole reason nutrition is
in this app — it is what separates "the block stalled from too much load" from
"the block stalled from too little food" — and Yazio already computes the target
and ships it in the same payload as the meals.

Revision ID: f7b2d5e9a1c4
Revises: e6a1c4d8b3f5
Create Date: 2026-08-24 16:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7b2d5e9a1c4"
down_revision: str | None = "e6a1c4d8b3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: rows imported before this existed have no target, and inventing
    # one would read as a measurement.
    op.add_column(
        "nutrition_days", sa.Column("energy_goal_kcal", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("nutrition_days", "energy_goal_kcal")
