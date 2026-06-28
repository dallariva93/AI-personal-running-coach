"""strava integration: accounts, webhook event inbox, activity id

Revision ID: b5d8e3f1a2c9
Revises: a3f1c9e2d4b8
Create Date: 2026-06-28 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5d8e3f1a2c9"
down_revision: str | None = "a3f1c9e2d4b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New external-id column + unique constraint on activities.
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("strava_activity_id", sa.String(length=64), nullable=True))
        batch_op.create_index(
            "ix_activities_strava_activity_id", ["strava_activity_id"], unique=False
        )
        batch_op.create_unique_constraint("uq_activity_strava_id", ["strava_activity_id"])

    op.create_table(
        "strava_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.String(length=128), nullable=False),
        sa.Column("refresh_token", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=True),
        sa.Column("athlete_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("athlete_id", name="uq_strava_athlete_id"),
    )
    op.create_index("ix_strava_accounts_athlete_id", "strava_accounts", ["athlete_id"])

    op.create_table(
        "strava_webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("object_type", sa.String(length=16), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=False),
        sa.Column("aspect_type", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("event_time", sa.Integer(), nullable=False),
        sa.Column("updates", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strava_webhook_events_object_id", "strava_webhook_events", ["object_id"]
    )
    op.create_index(
        "ix_strava_webhook_events_owner_id", "strava_webhook_events", ["owner_id"]
    )
    op.create_index(
        "ix_strava_webhook_events_status", "strava_webhook_events", ["status"]
    )


def downgrade() -> None:
    op.drop_table("strava_webhook_events")
    op.drop_index("ix_strava_accounts_athlete_id", table_name="strava_accounts")
    op.drop_table("strava_accounts")
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_constraint("uq_activity_strava_id", type_="unique")
        batch_op.drop_index("ix_activities_strava_activity_id")
        batch_op.drop_column("strava_activity_id")
