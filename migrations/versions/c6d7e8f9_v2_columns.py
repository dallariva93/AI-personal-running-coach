"""v2 columns: execution_detail, priority, expected_outcome, engine_version

Revision ID: c6d7e8f9
Revises: b5c6d7e8
Create Date: 2026-07-01 19:00:00.000000

Adds:
- training_plan_sessions.execution_detail (JSON) for multi-dimensional sub-scores
- coach_events.priority (String) for notification priority levels
- coach_decisions.expected_outcome (Text) for feedback loop
- coach_decisions.engine_version (String) for decision engine versioning
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9"
down_revision: str | None = "b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("training_plan_sessions") as batch_op:
        batch_op.add_column(sa.Column("execution_detail", sa.JSON(), nullable=True))

    with op.batch_alter_table("coach_events") as batch_op:
        batch_op.add_column(sa.Column("priority", sa.String(length=16), nullable=True))

    with op.batch_alter_table("coach_decisions") as batch_op:
        batch_op.add_column(sa.Column("expected_outcome", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("engine_version", sa.String(length=16), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("coach_decisions") as batch_op:
        batch_op.drop_column("engine_version")
        batch_op.drop_column("expected_outcome")

    with op.batch_alter_table("coach_events") as batch_op:
        batch_op.drop_column("priority")

    with op.batch_alter_table("training_plan_sessions") as batch_op:
        batch_op.drop_column("execution_detail")
