"""daily wellness native snapshot table

Revision ID: d4e5f6a7b8c9
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-08 14:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = '0a1b2c3d4e5f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'daily_wellness',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('sleep_seconds', sa.Integer(), nullable=True),
        sa.Column('sleep_score', sa.Integer(), nullable=True),
        sa.Column('hrv_last_night_avg', sa.Float(), nullable=True),
        sa.Column('hrv_status', sa.String(length=32), nullable=True),
        sa.Column('resting_hr', sa.Integer(), nullable=True),
        sa.Column('body_battery_charged', sa.Integer(), nullable=True),
        sa.Column('body_battery_drained', sa.Integer(), nullable=True),
        sa.Column('stress_avg', sa.Integer(), nullable=True),
        sa.Column('training_readiness_score', sa.Integer(), nullable=True),
        sa.Column('training_readiness_level', sa.String(length=32), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', name='uq_daily_wellness_date'),
    )
    op.create_index(
        op.f('ix_daily_wellness_date'),
        'daily_wellness',
        ['date'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_daily_wellness_date'), table_name='daily_wellness')
    op.drop_table('daily_wellness')
