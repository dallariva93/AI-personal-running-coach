"""activity laps (structured per-lap data, not just per-km splits)

An interval session is unreadable once its repetitions are averaged into whole
kilometres: a 500 m repetition and its 200 m jog both disappear into "the third
kilometre". The Garmin splits payload already carries the real laps — this
column stores them instead of discarding them.

Revision ID: c4e8f1a2b6d3
Revises: b3d5f7a9c1e2
Create Date: 2026-07-28 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8f1a2b6d3"
down_revision: str | None = "b3d5f7a9c1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("laps", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("activities", "laps")
