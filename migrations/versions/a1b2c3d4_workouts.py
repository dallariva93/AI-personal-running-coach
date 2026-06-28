"""workout templates and segments

Revision ID: a1b2c3d4
Revises: e1f4a7b2c8d3
Create Date: 2026-06-28 13:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4"
down_revision: str | None = "e1f4a7b2c8d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "type", sa.String(length=32), nullable=False, server_default="custom"
        ),
        sa.Column("estimated_distance_km", sa.Float(), nullable=True),
        sa.Column("estimated_duration_min", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "workout_segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workout_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("segment_type", sa.String(length=32), nullable=False),
        sa.Column(
            "repetitions", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("work_duration_sec", sa.Float(), nullable=True),
        sa.Column("work_distance_km", sa.Float(), nullable=True),
        sa.Column("work_pace", sa.String(length=16), nullable=True),
        sa.Column("rest_duration_sec", sa.Float(), nullable=True),
        sa.Column("rest_type", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workout_id"], ["workout_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("workout_segments")
    op.drop_table("workout_templates")
