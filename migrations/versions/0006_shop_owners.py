"""Shop owners: allow more than one Telegram account to manage a shop

Revision ID: 0006_shop_owners
Revises: 0005_shop_product_listings
Create Date: 2026-08-15 10:00:00.000000

shops.owner_tg_id holds a single account, which cannot represent a shop run by
two or more people. This adds the join table and backfills it from the existing
column. The column itself is deliberately left in place: seed data and the
existing lookup path still populate/read it, and dropping it would be a
breaking change for no benefit while both are honoured on lookup.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_shop_owners"
down_revision: str | None = "0005_shop_product_listings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shop_owners",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.BigInteger(), nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
            ["shop_id"], ["shops.id"], name="fk_shop_owners_shop_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_shop_owners"),
        sa.UniqueConstraint("shop_id", "tg_id", name="uq_shop_owners_shop_tg"),
    )
    op.create_index("ix_shop_owners_shop_id", "shop_owners", ["shop_id"])
    op.create_index("ix_shop_owners_tg_id", "shop_owners", ["tg_id"])

    # Backfill so shops that already had an owner keep working through the new path.
    op.execute(
        """
        INSERT INTO shop_owners (shop_id, tg_id, is_active)
        SELECT id, owner_tg_id, true FROM shops WHERE owner_tg_id IS NOT NULL
        ON CONFLICT (shop_id, tg_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_shop_owners_tg_id", table_name="shop_owners")
    op.drop_index("ix_shop_owners_shop_id", table_name="shop_owners")
    op.drop_table("shop_owners")
