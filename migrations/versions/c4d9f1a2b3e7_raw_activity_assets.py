"""raw activity assets archive table

Revision ID: c4d9f1a2b3e7
Revises: 8c7fc8a12013
Create Date: 2026-06-26 17:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d9f1a2b3e7'
down_revision: str | None = '8c7fc8a12013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'raw_activity_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('garmin_activity_id', sa.String(length=64), nullable=False),
        sa.Column('activity_type_key', sa.String(length=64), nullable=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('s3_key', sa.String(length=512), nullable=False),
        sa.Column('content_type', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'garmin_activity_id', 'kind', name='uq_raw_asset_activity_kind'
        ),
    )
    op.create_index(
        op.f('ix_raw_activity_assets_garmin_activity_id'),
        'raw_activity_assets',
        ['garmin_activity_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_raw_activity_assets_activity_type_key'),
        'raw_activity_assets',
        ['activity_type_key'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_raw_activity_assets_activity_type_key'),
        table_name='raw_activity_assets',
    )
    op.drop_index(
        op.f('ix_raw_activity_assets_garmin_activity_id'),
        table_name='raw_activity_assets',
    )
    op.drop_table('raw_activity_assets')
