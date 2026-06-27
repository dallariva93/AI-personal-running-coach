"""add altitude_profile and route_polyline to activities

Revision ID: a3f1c9e2d4b8
Revises: d7e2b9c4f1a8
Create Date: 2026-06-27 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f1c9e2d4b8"
down_revision: str | None = "d7e2b9c4f1a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("altitude_profile", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("route_polyline", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_column("route_polyline")
        batch_op.drop_column("altitude_profile")
