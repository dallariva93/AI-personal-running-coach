"""add athlete_model table (Digital Twin v0, A5)

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-07-03 11:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "athlete_model",
        sa.Column("key", sa.String(length=48), primary_key=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("athlete_model")
