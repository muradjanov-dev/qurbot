"""Shop product listings: photos, description, stock qty, durable drafts and photo blobs

Revision ID: 0005_shop_product_listings
Revises: 0004_canonical_product_image_url
Create Date: 2026-08-14 10:00:00.000000

Adds the owner-supplied listing fields to shop_products, plus two tables that
exist so uploaded work is never lost: shop_product_drafts (the wizard writes
every answer here before asking the next question) and product_photo_blobs
(the photo bytes, so a listing does not depend on a Telegram file_id that dies
with the bot token).

moderation_status defaults to 'approved' so the existing offer rows -- which
carry no owner-supplied media to review -- keep behaving exactly as before;
only the wizard sets 'pending'.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_shop_product_listings"
down_revision: str | None = "0004_canonical_product_image_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("shop_products", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "shop_products",
        sa.Column(
            "photos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("shop_products", sa.Column("stock_qty", sa.Numeric(14, 4), nullable=True))
    op.add_column(
        "shop_products", sa.Column("proposed_category_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "shop_products",
        sa.Column(
            "moderation_status",
            sa.String(length=32),
            server_default="approved",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_shop_products_proposed_category",
        "shop_products",
        "categories",
        ["proposed_category_id"],
        ["id"],
    )
    # Admin moderation queue reads only the small pending slice; a partial index
    # keeps it off the 4k+ approved rows.
    op.create_index(
        "ix_shop_products_moderation_pending",
        "shop_products",
        ["updated_at"],
        postgresql_where=sa.text("moderation_status = 'pending'"),
    )

    op.create_table(
        "shop_product_drafts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pack_size", sa.Numeric(14, 4), nullable=True),
        sa.Column("pack_unit_code", sa.String(length=32), nullable=True),
        sa.Column("price_per_pack", sa.Numeric(14, 2), nullable=True),
        sa.Column("stock_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column(
            "photos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "visited_steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("matched_canonical_id", sa.BigInteger(), nullable=True),
        sa.Column("match_confidence", sa.Numeric(3, 2), nullable=True),
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
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["pack_unit_code"], ["units.code"]),
        sa.ForeignKeyConstraint(["matched_canonical_id"], ["canonical_products.id"]),
        sa.ForeignKeyConstraint(["applied_shop_product_id"], ["shop_products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shop_product_drafts_shop_id", "shop_product_drafts", ["shop_id"])
    op.create_index("ix_shop_product_drafts_owner_tg_id", "shop_product_drafts", ["owner_tg_id"])
    op.create_index("ix_shop_product_drafts_status", "shop_product_drafts", ["status"])
    op.create_index(
        "ix_shop_product_drafts_owner_status", "shop_product_drafts", ["owner_tg_id", "status"]
    )

    op.create_table(
        "product_photo_blobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_unique_id", sa.String(length=128), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(length=64), server_default="image/jpeg", nullable=False),
        sa.Column("byte_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_unique_id", name="uq_product_photo_blobs_file_unique_id"),
    )
    op.create_index(
        "ix_product_photo_blobs_file_unique_id", "product_photo_blobs", ["file_unique_id"]
    )
    op.create_index("ix_product_photo_blobs_shop_id", "product_photo_blobs", ["shop_id"])


def downgrade() -> None:
    op.drop_index("ix_product_photo_blobs_shop_id", table_name="product_photo_blobs")
    op.drop_index("ix_product_photo_blobs_file_unique_id", table_name="product_photo_blobs")
    op.drop_table("product_photo_blobs")

    op.drop_index("ix_shop_product_drafts_owner_status", table_name="shop_product_drafts")
    op.drop_index("ix_shop_product_drafts_status", table_name="shop_product_drafts")
    op.drop_index("ix_shop_product_drafts_owner_tg_id", table_name="shop_product_drafts")
    op.drop_index("ix_shop_product_drafts_shop_id", table_name="shop_product_drafts")
    op.drop_table("shop_product_drafts")

    op.drop_index("ix_shop_products_moderation_pending", table_name="shop_products")
    op.drop_constraint("fk_shop_products_proposed_category", "shop_products", type_="foreignkey")
    op.drop_column("shop_products", "moderation_status")
    op.drop_column("shop_products", "proposed_category_id")
    op.drop_column("shop_products", "stock_qty")
    op.drop_column("shop_products", "photos")
    op.drop_column("shop_products", "description")
