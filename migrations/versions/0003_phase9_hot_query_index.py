"""Phase 9: replace shop_products indexes with one covering the hot quote query

Revision ID: 0003_phase9_hot_query_index
Revises: 0002_phase8_ops
Create Date: 2026-08-13 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_phase9_hot_query_index"
down_revision: str | None = "0002_phase8_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_shop_products_canonical_base_price", table_name="shop_products")
    op.drop_index("ix_shop_products_active_fresh", table_name="shop_products")
    op.create_index(
        "ix_shop_products_active_fresh",
        "shop_products",
        ["canonical_id", "price_per_base_unit"],
        postgresql_where=sa.text(
            "is_active IS TRUE AND staleness_state <> 'stale' AND stock_status <> 'out'"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_shop_products_active_fresh", table_name="shop_products")
    op.create_index(
        "ix_shop_products_active_fresh",
        "shop_products",
        ["canonical_id", "is_active", "staleness_state"],
        postgresql_where=sa.text("is_active IS TRUE AND staleness_state <> 'stale'"),
    )
    op.create_index(
        "ix_shop_products_canonical_base_price",
        "shop_products",
        ["canonical_id", "price_per_base_unit"],
    )
