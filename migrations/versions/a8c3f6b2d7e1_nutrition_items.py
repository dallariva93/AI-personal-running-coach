"""nutrition: the item-by-item food diary

The daily totals answer "did the fuelling match the load". They do not answer
"what did I actually eat", which is the question behind "why am I short on
carbs" — and that needs the entries themselves.

Two tables, because Yazio's diary references catalogue products by UUID only:
the entries, and a name cache so the same yogurt is not re-fetched every
morning.

Revision ID: a8c3f6b2d7e1
Revises: f7b2d5e9a1c4
Create Date: 2026-08-24 16:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8c3f6b2d7e1"
down_revision: str | None = "f7b2d5e9a1c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "yazio_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("producer", sa.String(length=255), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("product_id", name="uq_yazio_product_id"),
    )
    op.create_index("ix_yazio_products_product_id", "yazio_products", ["product_id"])

    op.create_table(
        "nutrition_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Yazio's own entry id: re-importing a day must not duplicate rows.
        sa.Column("yazio_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.String(length=10), nullable=False),
        sa.Column("meal", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("product_id", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("serving", sa.String(length=64), nullable=True),
        sa.Column("energy_kcal", sa.Float(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("yazio_id", name="uq_nutrition_item_yazio_id"),
    )
    op.create_index("ix_nutrition_items_date", "nutrition_items", ["date"])
    op.create_index("ix_nutrition_items_product_id", "nutrition_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_nutrition_items_product_id", table_name="nutrition_items")
    op.drop_index("ix_nutrition_items_date", table_name="nutrition_items")
    op.drop_table("nutrition_items")
    op.drop_index("ix_yazio_products_product_id", table_name="yazio_products")
    op.drop_table("yazio_products")
