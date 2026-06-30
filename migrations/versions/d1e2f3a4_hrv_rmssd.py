"""add hrv_rmssd to daily_checkins

Revision ID: d1e2f3a4
Revises: c5d6e7f8
Create Date: 2026-06-30 12:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4"
down_revision: str | None = "c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("daily_checkins") as batch_op:
        batch_op.add_column(sa.Column("hrv_rmssd", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("daily_checkins") as batch_op:
        batch_op.drop_column("hrv_rmssd")
