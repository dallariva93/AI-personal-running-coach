"""add source (provenance) to daily_checkins

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-07-03 09:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("daily_checkins") as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("daily_checkins") as batch_op:
        batch_op.drop_column("source")
