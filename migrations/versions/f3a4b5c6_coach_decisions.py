"""coach decisions table + adaptive-plan columns on plan sessions

Revision ID: f3a4b5c6
Revises: e2f3a4b5
Create Date: 2026-07-01 10:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6"
down_revision: str | None = "e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coach_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("headline", sa.String(length=160), nullable=False),
        sa.Column("prescription", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("missing_data", sa.JSON(), nullable=True),
        sa.Column("alternatives", sa.JSON(), nullable=True),
        sa.Column("safety_flags", sa.JSON(), nullable=True),
        sa.Column("plan_session_id", sa.Integer(), nullable=True),
        sa.Column("session_type", sa.String(length=32), nullable=True),
        sa.Column("target_distance_km", sa.Float(), nullable=True),
        sa.Column("target_pace", sa.String(length=16), nullable=True),
        sa.Column("target_duration_min", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="rules"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("date", name="uq_coach_decision_date"),
    )
    op.create_index("ix_coach_decisions_date", "coach_decisions", ["date"])

    with op.batch_alter_table("training_plan_sessions") as batch_op:
        batch_op.add_column(sa.Column("base_target_distance_km", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("base_session_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("adjustment_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("training_plan_sessions") as batch_op:
        batch_op.drop_column("adjustment_note")
        batch_op.drop_column("base_session_type")
        batch_op.drop_column("base_target_distance_km")

    op.drop_index("ix_coach_decisions_date", table_name="coach_decisions")
    op.drop_table("coach_decisions")
