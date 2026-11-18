"""yazio account + daily nutrition

Nutrition closes a loop the running data alone cannot: a block that stalls
because of an energy deficit looks exactly like one that stalls from too much
load, and the coach would blame the training.

Two tables, deliberately separate: the account holds encrypted OAuth tokens
(same shape as ``strava_accounts``), the nutrition rows hold one aggregate per
day. Disconnecting Yazio must be able to drop the tokens without losing the
history already imported.

Revision ID: e6a1c4d8b3f5
Revises: d5f9a3b7c2e4
Create Date: 2026-08-19 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6a1c4d8b3f5"
down_revision: str | None = "d5f9a3b7c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "yazio_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Text: these hold Fernet ciphertext, not the raw tokens.
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "nutrition_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.String(length=10), nullable=False),
        # All nullable: a partially logged day is real data about a partial log,
        # while a zero would read as "ate nothing".
        sa.Column("energy_kcal", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("water_ml", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="yazio"),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("date", name="uq_nutrition_date"),
    )
    op.create_index("ix_nutrition_days_date", "nutrition_days", ["date"])


def downgrade() -> None:
    op.drop_index("ix_nutrition_days_date", table_name="nutrition_days")
    op.drop_table("nutrition_days")
    op.drop_table("yazio_accounts")
