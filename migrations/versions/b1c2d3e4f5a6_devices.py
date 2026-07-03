"""devices table for FCM push notifications (Roadmap A3)

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-07-03 12:00:00.000000
"""
from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fcm_token", sa.String(length=512), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False, server_default="android"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # Match the ORM: `mapped_column(unique=True, index=True)` emits one UNIQUE
    # named index, not a non-unique index + a separate constraint (which left
    # `alembic check` dirty). Unique because a device's FCM token is its key.
    op.create_index("ix_devices_fcm_token", "devices", ["fcm_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_devices_fcm_token", table_name="devices")
    op.drop_table("devices")
