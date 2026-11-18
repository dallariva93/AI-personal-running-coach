"""plan sessions: structured steps + garmin export bookkeeping

The periodization engine already computed the repetitions, their distance and
the recovery — and then spent them on a description string. Anything wanting to
use those numbers (a watch export, a stricter execution score) had to parse
Italian prose back into integers, which is the kind of guessing that produces
plausible wrong answers.

``garmin_workout_id`` exists so a second export updates the workout it already
created instead of stacking duplicates in the athlete's calendar.

Revision ID: b9d4e7a1c3f8
Revises: a8c3f6b2d7e1
Create Date: 2026-08-24 17:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9d4e7a1c3f8"
down_revision: str | None = "a8c3f6b2d7e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("training_plan_sessions", sa.Column("steps", sa.JSON(), nullable=True))
    op.add_column(
        "training_plan_sessions",
        sa.Column("garmin_workout_id", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "training_plan_sessions",
        sa.Column("garmin_scheduled_date", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("training_plan_sessions", "garmin_scheduled_date")
    op.drop_column("training_plan_sessions", "garmin_workout_id")
    op.drop_column("training_plan_sessions", "steps")
