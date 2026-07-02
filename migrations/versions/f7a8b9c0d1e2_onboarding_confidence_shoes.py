"""onboarding, report confidence, shoe tracking (Roadmap #4, #5, #6)

Revision ID: f7a8b9c0d1e2
Revises: c6d7e8f9
Create Date: 2026-07-15 10:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Feature 5: confidence + missing_data on coaching_reports
    op.add_column(
        "coaching_reports",
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
    )
    op.add_column(
        "coaching_reports",
        sa.Column("missing_data", sa.JSON(), nullable=True),
    )

    # Feature 6: shoe_id on activities
    op.add_column(
        "activities",
        sa.Column("shoe_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_activities_shoe_id", "activities", ["shoe_id"])

    # Feature 6: shoes table
    op.create_table(
        "shoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("brand", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("purchase_date", sa.String(length=10), nullable=True),
        sa.Column("max_km", sa.Float(), nullable=False, server_default="800.0"),
        sa.Column("retired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shoes")
    op.drop_index("ix_activities_shoe_id", table_name="activities")
    op.drop_column("activities", "shoe_id")
    op.drop_column("coaching_reports", "missing_data")
    op.drop_column("coaching_reports", "confidence")
