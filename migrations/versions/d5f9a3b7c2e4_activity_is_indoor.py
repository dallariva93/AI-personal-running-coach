"""activity is_indoor (treadmill runs)

A treadmill run reaches the app as a normal run — Garmin's typeKey is
``treadmill_running`` / ``indoor_running`` and Strava keeps sport_type "Run"
with ``trainer: true``, so both pass the "is this running?" filter. Nothing
recorded that it happened indoors, which let the weather lookup attach the
street's temperature to a session run in an air-conditioned gym.

Revision ID: d5f9a3b7c2e4
Revises: c4e8f1a2b6d3
Create Date: 2026-07-30 11:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f9a3b7c2e4"
down_revision: str | None = "c4e8f1a2b6d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("is_indoor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("activities", "is_indoor")
