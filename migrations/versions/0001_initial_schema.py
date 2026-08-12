"""Initial schema with extensions, tables, and indexes

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-13 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin";')

    # 2. Units
    op.create_table(
        "units",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name_uz", sa.String(length=100), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("base_code", sa.String(length=32), nullable=True),
        sa.Column(
            "factor_to_base",
            sa.Numeric(precision=14, scale=4),
            nullable=False,
            server_default="1.0000",
        ),
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
        sa.ForeignKeyConstraint(["base_code"], ["units.code"], name="fk_units_base_code_units"),
        sa.PrimaryKeyConstraint("code", name="pk_units"),
    )

    # 3. Categories
    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name_uz", sa.String(length=255), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icon", sa.String(length=32), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["parent_id"], ["categories.id"], name="fk_categories_parent_id_categories"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
    )
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    # 4. Canonical Products
    op.create_table(
        "canonical_products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name_uz", sa.String(length=255), nullable=False),
        sa.Column("name_uz_cyrl", sa.String(length=255), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("base_unit_code", sa.String(length=32), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("tier", sa.String(length=32), nullable=False, server_default="standard"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("search_doc", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["base_unit_code"], ["units.code"], name="fk_canonical_products_base_unit_code_units"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name="fk_canonical_products_category_id_categories"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_canonical_products"),
    )
    op.create_index("ix_canonical_products_slug", "canonical_products", ["slug"], unique=True)
    op.create_index("ix_canonical_products_category_id", "canonical_products", ["category_id"])
    op.create_index("ix_canonical_products_brand", "canonical_products", ["brand"])
    op.create_index("ix_canonical_products_is_active", "canonical_products", ["is_active"])
    op.create_index(
        "ix_canonical_products_search_doc_trgm",
        "canonical_products",
        ["search_doc"],
        postgresql_using="gin",
        postgresql_ops={"search_doc": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_canonical_products_attributes_jsonb",
        "canonical_products",
        ["attributes"],
        postgresql_using="gin",
        postgresql_ops={"attributes": "jsonb_path_ops"},
    )

    # 5. Product Aliases
    op.create_table(
        "product_aliases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("canonical_id", sa.BigInteger(), nullable=False),
        sa.Column("alias_norm", sa.String(length=255), nullable=False),
        sa.Column("alias_raw", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="seed"),
        sa.Column(
            "confidence", sa.Numeric(precision=3, scale=2), nullable=False, server_default="1.00"
        ),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.ForeignKeyConstraint(
            ["canonical_id"],
            ["canonical_products.id"],
            name="fk_product_aliases_canonical_id_canonical_products",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_aliases"),
        sa.UniqueConstraint(
            "canonical_id", "alias_norm", name="uq_product_aliases_canonical_alias_norm"
        ),
    )
    op.create_index("ix_product_aliases_canonical_id", "product_aliases", ["canonical_id"])
    op.create_index("ix_product_aliases_alias_norm", "product_aliases", ["alias_norm"])
    op.create_index("ix_product_aliases_is_approved", "product_aliases", ["is_approved"])
    op.create_index(
        "ix_product_aliases_alias_norm_approved",
        "product_aliases",
        ["alias_norm"],
        unique=True,
        postgresql_where=sa.text("is_approved IS TRUE"),
    )

    # 6. Districts
    op.create_table(
        "districts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False, server_default="Toshkent"),
        sa.Column("name_uz", sa.String(length=100), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column("centroid_lat", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("centroid_lng", sa.Numeric(precision=10, scale=7), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_districts"),
    )

    # 7. Shops
    op.create_table(
        "shops",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("district_id", sa.BigInteger(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("lat", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("lng", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rating", sa.Numeric(precision=3, scale=2), nullable=False, server_default="5.00"
        ),
        sa.Column(
            "trust_score", sa.Numeric(precision=3, scale=2), nullable=False, server_default="1.00"
        ),
        sa.Column(
            "working_hours",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "payment_methods",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name="fk_shops_district_id_districts"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shops"),
    )
    op.create_index("ix_shops_name", "shops", ["name"])
    op.create_index("ix_shops_district_id", "shops", ["district_id"])
    op.create_index("ix_shops_owner_tg_id", "shops", ["owner_tg_id"])
    op.create_index("ix_shops_is_active", "shops", ["is_active"])

    # 8. Shop Delivery Rules
    op.create_table(
        "shop_delivery_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("district_id", sa.BigInteger(), nullable=True),
        sa.Column("fee", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"),
        sa.Column("free_above", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column(
            "min_order", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"
        ),
        sa.Column("eta_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("same_day_cutoff", sa.Time(), nullable=True),
        sa.Column("is_pickup_only", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name="fk_shop_delivery_rules_district_id_districts"
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name="fk_shop_delivery_rules_shop_id_shops"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shop_delivery_rules"),
    )
    op.create_index("ix_shop_delivery_rules_shop_id", "shop_delivery_rules", ["shop_id"])
    op.create_index("ix_shop_delivery_rules_district_id", "shop_delivery_rules", ["district_id"])

    # 9. Shop Products (Offers)
    op.create_table(
        "shop_products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_id", sa.BigInteger(), nullable=True),
        sa.Column("raw_name", sa.String(length=255), nullable=False),
        sa.Column("raw_unit", sa.String(length=50), nullable=False),
        sa.Column(
            "pack_size", sa.Numeric(precision=14, scale=4), nullable=False, server_default="1.0000"
        ),
        sa.Column("pack_unit_code", sa.String(length=32), nullable=True),
        sa.Column("price_per_pack", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("price_per_base_unit", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="UZS"),
        sa.Column("stock_status", sa.String(length=32), nullable=False, server_default="in_stock"),
        sa.Column(
            "min_qty", sa.Numeric(precision=14, scale=4), nullable=False, server_default="1.0000"
        ),
        sa.Column("updated_by", sa.String(length=32), nullable=False, server_default="shop"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("staleness_state", sa.String(length=32), nullable=False, server_default="fresh"),
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
        sa.ForeignKeyConstraint(
            ["canonical_id"],
            ["canonical_products.id"],
            name="fk_shop_products_canonical_id_canonical_products",
        ),
        sa.ForeignKeyConstraint(
            ["pack_unit_code"], ["units.code"], name="fk_shop_products_pack_unit_code_units"
        ),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], name="fk_shop_products_shop_id_shops"),
        sa.PrimaryKeyConstraint("id", name="pk_shop_products"),
        sa.UniqueConstraint(
            "shop_id", "canonical_id", "pack_size", "pack_unit_code", name="uq_shop_products_offer"
        ),
    )
    op.create_index("ix_shop_products_shop_id", "shop_products", ["shop_id"])
    op.create_index("ix_shop_products_canonical_id", "shop_products", ["canonical_id"])
    op.create_index(
        "ix_shop_products_canonical_base_price",
        "shop_products",
        ["canonical_id", "price_per_base_unit"],
    )
    op.create_index("ix_shop_products_updated_at", "shop_products", ["updated_at"])
    op.create_index(
        "ix_shop_products_active_fresh",
        "shop_products",
        ["canonical_id", "is_active", "staleness_state"],
        postgresql_where=sa.text("is_active IS TRUE AND staleness_state <> 'stale'"),
    )

    # 10. Price History
    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_product_id", sa.BigInteger(), nullable=False),
        sa.Column("price_per_pack", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("price_per_base_unit", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["shop_product_id"],
            ["shop_products.id"],
            name="fk_price_history_shop_product_id_shop_products",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_price_history"),
    )
    op.create_index("ix_price_history_shop_product_id", "price_history", ["shop_product_id"])
    op.create_index("ix_price_history_recorded_at", "price_history", ["recorded_at"])

    # 11. Import Batches & Rows
    op.create_table(
        "import_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], name="fk_import_batches_shop_id_shops"),
        sa.PrimaryKeyConstraint("id", name="pk_import_batches"),
    )
    op.create_index("ix_import_batches_shop_id", "import_batches", ["shop_id"])

    op.create_table(
        "import_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("matched_canonical_id", sa.BigInteger(), nullable=True),
        sa.Column("match_confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("resolution", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("applied_shop_product_id", sa.BigInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["applied_shop_product_id"],
            ["shop_products.id"],
            name="fk_import_rows_applied_shop_product_id_shop_products",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["import_batches.id"], name="fk_import_rows_batch_id_import_batches"
        ),
        sa.ForeignKeyConstraint(
            ["matched_canonical_id"],
            ["canonical_products.id"],
            name="fk_import_rows_matched_canonical_id_canonical_products",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_rows"),
    )
    op.create_index("ix_import_rows_batch_id", "import_rows", ["batch_id"])

    # 12. Users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("lang", sa.String(length=16), nullable=False, server_default="uz_latn"),
        sa.Column("district_id", sa.BigInteger(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="customer"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referral_source", sa.String(length=100), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name="fk_users_district_id_districts"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_tg_id", "users", ["tg_id"], unique=True)
    op.create_index("ix_users_district_id", "users", ["district_id"])

    # 13. Baskets & Lines
    op.create_table(
        "baskets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="parsing"),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_baskets_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_baskets"),
    )
    op.create_index("ix_baskets_user_id", "baskets", ["user_id"])

    op.create_table(
        "basket_lines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("basket_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_name", sa.String(length=255), nullable=False),
        sa.Column("qty", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("unit_code", sa.String(length=32), nullable=True),
        sa.Column("canonical_id", sa.BigInteger(), nullable=True),
        sa.Column("match_confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("match_method", sa.String(length=32), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("user_note", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["basket_id"], ["baskets.id"], name="fk_basket_lines_basket_id_baskets"
        ),
        sa.ForeignKeyConstraint(
            ["canonical_id"],
            ["canonical_products.id"],
            name="fk_basket_lines_canonical_id_canonical_products",
        ),
        sa.ForeignKeyConstraint(
            ["unit_code"], ["units.code"], name="fk_basket_lines_unit_code_units"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_basket_lines"),
    )
    op.create_index("ix_basket_lines_basket_id", "basket_lines", ["basket_id"])
    op.create_index("ix_basket_lines_canonical_id", "basket_lines", ["canonical_id"])

    # 14. Quotes
    op.create_table(
        "quotes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("basket_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("items_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("delivery_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("grand_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("coverage_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("shop_count", sa.Integer(), nullable=False),
        sa.Column("eta_hours", sa.Integer(), nullable=True),
        sa.Column(
            "missing_line_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.ForeignKeyConstraint(["basket_id"], ["baskets.id"], name="fk_quotes_basket_id_baskets"),
        sa.PrimaryKeyConstraint("id", name="pk_quotes"),
    )
    op.create_index("ix_quotes_basket_id", "quotes", ["basket_id"])

    # 15. Orders, Shop Parts & Items
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("quote_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("contact_phone", sa.String(length=50), nullable=False),
        sa.Column("delivery_address", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("grand_total_quoted", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("grand_total_final", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], name="fk_orders_quote_id_quotes"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_orders_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
    )
    op.create_index("ix_orders_quote_id", "orders", ["quote_id"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])

    op.create_table(
        "order_shop_parts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "delivery_fee", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("shop_response", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name="fk_order_shop_parts_order_id_orders"
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name="fk_order_shop_parts_shop_id_shops"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_shop_parts"),
    )
    op.create_index("ix_order_shop_parts_order_id", "order_shop_parts", ["order_id"])
    op.create_index("ix_order_shop_parts_shop_id", "order_shop_parts", ["shop_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_shop_part_id", sa.BigInteger(), nullable=False),
        sa.Column("canonical_id", sa.BigInteger(), nullable=False),
        sa.Column("shop_product_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("unit_code", sa.String(length=32), nullable=False),
        sa.Column("unit_price_quoted", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("fulfilled_qty", sa.Numeric(precision=14, scale=4), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["canonical_id"],
            ["canonical_products.id"],
            name="fk_order_items_canonical_id_canonical_products",
        ),
        sa.ForeignKeyConstraint(
            ["order_shop_part_id"],
            ["order_shop_parts.id"],
            name="fk_order_items_order_shop_part_id_order_shop_parts",
        ),
        sa.ForeignKeyConstraint(
            ["shop_product_id"],
            ["shop_products.id"],
            name="fk_order_items_shop_product_id_shop_products",
        ),
        sa.ForeignKeyConstraint(
            ["unit_code"], ["units.code"], name="fk_order_items_unit_code_units"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_items"),
    )
    op.create_index("ix_order_items_order_shop_part_id", "order_items", ["order_shop_part_id"])

    # 16. Ops: Unmatched Queries, LLM Calls, Events
    op.create_table(
        "unmatched_queries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("suggested_canonical_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("resolved_alias_id", sa.BigInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["resolved_alias_id"],
            ["product_aliases.id"],
            name="fk_unmatched_queries_resolved_alias_id_product_aliases",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_canonical_id"],
            ["canonical_products.id"],
            name="fk_unmatched_queries_suggested_canonical_id_canonical_products",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_unmatched_queries_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_unmatched_queries"),
    )
    op.create_index(
        "ix_unmatched_queries_normalized", "unmatched_queries", ["normalized"], unique=True
    )
    op.create_index("ix_unmatched_queries_user_id", "unmatched_queries", ["user_id"])

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cost_usd", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0.000000"
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("raw_response", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_llm_calls"),
    )
    op.create_index("ix_llm_calls_input_hash", "llm_calls", ["input_hash"])

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_events_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_name", "events", ["name"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("llm_calls")
    op.drop_table("unmatched_queries")
    op.drop_table("order_items")
    op.drop_table("order_shop_parts")
    op.drop_table("orders")
    op.drop_table("quotes")
    op.drop_table("basket_lines")
    op.drop_table("baskets")
    op.drop_table("users")
    op.drop_table("import_rows")
    op.drop_table("import_batches")
    op.drop_table("price_history")
    op.drop_table("shop_products")
    op.drop_table("shop_delivery_rules")
    op.drop_table("shops")
    op.drop_table("districts")
    op.drop_table("product_aliases")
    op.drop_table("canonical_products")
    op.drop_table("categories")
    op.drop_table("units")

    op.execute('DROP EXTENSION IF EXISTS "btree_gin";')
    op.execute('DROP EXTENSION IF EXISTS "unaccent";')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm";')
