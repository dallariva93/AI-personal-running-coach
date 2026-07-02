"""activity start_time (Q6: weather-window optimizer + habitual hours)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-02 21:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("start_time", sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column("activities", "start_time")
