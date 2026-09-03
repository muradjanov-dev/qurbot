"""Volume pricing: a cheaper per-pack price from a given quantity upward

Revision ID: 0012_price_tiers
Revises: 0011_purge_seeded_catalog
Create Date: 2026-09-01 18:00:00.000000

Wholesale in this trade is quoted as a second price with a threshold -- "10.2$
a sheet, 10$ from 200 sheets" -- and until now there was nowhere to put the
second number. A customer ordering a lorry-load was quoted the retail price,
which is wrong in the direction that loses the order to a phone call.

Rows rather than a JSON column on the offer: the optimizer compares tiers
across shops, and a price a customer was quoted has to be auditable afterwards.

The unique constraint is what keeps a tier table sane -- two prices for the
same threshold on the same offer is not a discount, it is a bug that would make
quotes depend on row order.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_price_tiers"
down_revision = "0011_purge_seeded_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_product_price_tiers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_product_id", sa.BigInteger(), nullable=False),
        sa.Column("min_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("price_per_pack", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["shop_product_id"], ["shop_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_product_id", "min_qty", name="uq_price_tier_product_min_qty"),
    )
    op.create_index(
        "ix_shop_product_price_tiers_shop_product_id",
        "shop_product_price_tiers",
        ["shop_product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shop_product_price_tiers_shop_product_id", table_name="shop_product_price_tiers"
    )
    op.drop_table("shop_product_price_tiers")
