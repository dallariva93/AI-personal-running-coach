"""numeric aerobic/anaerobic training effect on activities

Revision ID: d7e2b9c4f1a8
Revises: c4d9f1a2b3e7
Create Date: 2026-06-26 19:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e2b9c4f1a8'
down_revision: str | None = 'c4d9f1a2b3e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aerobic_training_effect', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('anaerobic_training_effect', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.drop_column('anaerobic_training_effect')
        batch_op.drop_column('aerobic_training_effect')
