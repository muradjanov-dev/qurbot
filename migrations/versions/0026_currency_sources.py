"""Store source currencies while keeping quote prices materialized in UZS."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_currency_sources"
down_revision: str | None = "0025_telegram_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fx_rate_settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("usd_to_uzs_rate", sa.Numeric(14, 6), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_fx_rate_settings_singleton_id")),
        sa.CheckConstraint(
            "usd_to_uzs_rate IS NULL OR usd_to_uzs_rate > 0",
            name=op.f("ck_fx_rate_settings_positive_rate"),
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_fx_rate_settings_nonnegative_revision")),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO fx_rate_settings (id, usd_to_uzs_rate, revision, updated_at, updated_by)
            VALUES (1, 11820.48, 1, CURRENT_TIMESTAMP, NULL)
            """
        )
    )

    op.add_column(
        "shop_products",
        sa.Column("source_currency", sa.String(length=3), nullable=False, server_default="UZS"),
    )
    op.add_column(
        "shop_products",
        sa.Column("source_price_per_pack", sa.Numeric(16, 4), nullable=True),
    )
    op.add_column("shop_products", sa.Column("fx_rate_used", sa.Numeric(14, 6), nullable=True))
    op.add_column(
        "shop_products",
        sa.Column("fx_rate_revision", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.execute(
        sa.text(
            """
            UPDATE shop_products
            SET source_price_per_pack = price_per_pack,
                fx_rate_used = 1,
                fx_rate_revision = 0
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_shop_products_source_currency"),
        "shop_products",
        "source_currency IN ('UZS', 'USD')",
    )
    op.create_check_constraint(
        op.f("ck_shop_products_source_price_positive"),
        "shop_products",
        "source_price_per_pack IS NULL OR source_price_per_pack > 0",
    )
    op.create_check_constraint(
        op.f("ck_shop_products_usd_source_price_required"),
        "shop_products",
        "source_currency <> 'USD' OR source_price_per_pack IS NOT NULL",
    )
    op.create_index("ix_shop_products_source_currency", "shop_products", ["source_currency"])

    op.add_column(
        "shop_product_price_tiers",
        sa.Column("source_currency", sa.String(length=3), nullable=False, server_default="UZS"),
    )
    op.add_column(
        "shop_product_price_tiers",
        sa.Column("source_price_per_pack", sa.Numeric(16, 4), nullable=True),
    )
    op.add_column(
        "shop_product_price_tiers", sa.Column("fx_rate_used", sa.Numeric(14, 6), nullable=True)
    )
    op.add_column(
        "shop_product_price_tiers",
        sa.Column("fx_rate_revision", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.execute(
        sa.text(
            """
            UPDATE shop_product_price_tiers
            SET source_price_per_pack = price_per_pack,
                fx_rate_used = 1,
                fx_rate_revision = 0
            """
        )
    )
    op.create_check_constraint(
        op.f("ck_shop_product_price_tiers_source_currency"),
        "shop_product_price_tiers",
        "source_currency IN ('UZS', 'USD')",
    )
    op.create_check_constraint(
        op.f("ck_shop_product_price_tiers_source_price_positive"),
        "shop_product_price_tiers",
        "source_price_per_pack IS NULL OR source_price_per_pack > 0",
    )
    op.create_check_constraint(
        op.f("ck_shop_product_price_tiers_usd_source_price_required"),
        "shop_product_price_tiers",
        "source_currency <> 'USD' OR source_price_per_pack IS NOT NULL",
    )
    op.create_index(
        "ix_shop_product_price_tiers_source_currency",
        "shop_product_price_tiers",
        ["source_currency"],
    )

    op.add_column(
        "import_batches", sa.Column("source_currency", sa.String(length=3), nullable=True)
    )
    # Batches created before currency selection were all applied as UZS.
    op.execute(sa.text("UPDATE import_batches SET source_currency = 'UZS'"))
    op.create_check_constraint(
        op.f("ck_import_batches_source_currency"),
        "import_batches",
        "source_currency IS NULL OR source_currency IN ('UZS', 'USD')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_import_batches_source_currency"), "import_batches", type_="check")
    op.drop_column("import_batches", "source_currency")

    op.drop_index(
        "ix_shop_product_price_tiers_source_currency", table_name="shop_product_price_tiers"
    )
    op.drop_constraint(
        op.f("ck_shop_product_price_tiers_usd_source_price_required"),
        "shop_product_price_tiers",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_shop_product_price_tiers_source_price_positive"),
        "shop_product_price_tiers",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_shop_product_price_tiers_source_currency"),
        "shop_product_price_tiers",
        type_="check",
    )
    op.drop_column("shop_product_price_tiers", "fx_rate_revision")
    op.drop_column("shop_product_price_tiers", "fx_rate_used")
    op.drop_column("shop_product_price_tiers", "source_price_per_pack")
    op.drop_column("shop_product_price_tiers", "source_currency")

    op.drop_index("ix_shop_products_source_currency", table_name="shop_products")
    op.drop_constraint(
        op.f("ck_shop_products_usd_source_price_required"), "shop_products", type_="check"
    )
    op.drop_constraint(
        op.f("ck_shop_products_source_price_positive"), "shop_products", type_="check"
    )
    op.drop_constraint(op.f("ck_shop_products_source_currency"), "shop_products", type_="check")
    op.drop_column("shop_products", "fx_rate_revision")
    op.drop_column("shop_products", "fx_rate_used")
    op.drop_column("shop_products", "source_price_per_pack")
    op.drop_column("shop_products", "source_currency")

    op.drop_table("fx_rate_settings")
