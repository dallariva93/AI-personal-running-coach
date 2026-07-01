"""coach events audit log (decisions + adaptations) + notifications source

Revision ID: b5c6d7e8
Revises: a4b5c6d7
Create Date: 2026-07-01 14:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "b5c6d7e8"
down_revision: str | None = "a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coach_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("plan_session_id", sa.Integer(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column("notifiable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_coach_events_date", "coach_events", ["date"])
    op.create_index("ix_coach_events_event_type", "coach_events", ["event_type"])
    op.create_index("ix_coach_events_dedupe_key", "coach_events", ["dedupe_key"])
    op.create_index("ix_coach_events_created_at", "coach_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_coach_events_created_at", table_name="coach_events")
    op.drop_index("ix_coach_events_dedupe_key", table_name="coach_events")
    op.drop_index("ix_coach_events_event_type", table_name="coach_events")
    op.drop_index("ix_coach_events_date", table_name="coach_events")
    op.drop_table("coach_events")
