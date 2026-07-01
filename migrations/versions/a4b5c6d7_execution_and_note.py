"""workout execution columns + daily note on coach decisions

Revision ID: a4b5c6d7
Revises: f3a4b5c6
Create Date: 2026-07-01 12:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7"
down_revision: str | None = "f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("training_plan_sessions") as batch_op:
        batch_op.add_column(sa.Column("execution_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("execution_status", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("execution_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("execution_evidence", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("executed_activity_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("coach_decisions") as batch_op:
        batch_op.add_column(sa.Column("daily_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("coach_decisions") as batch_op:
        batch_op.drop_column("daily_note")

    with op.batch_alter_table("training_plan_sessions") as batch_op:
        batch_op.drop_column("executed_activity_id")
        batch_op.drop_column("execution_evidence")
        batch_op.drop_column("execution_note")
        batch_op.drop_column("execution_status")
        batch_op.drop_column("execution_score")
