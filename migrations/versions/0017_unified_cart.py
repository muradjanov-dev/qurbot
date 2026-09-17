"""Durable shared cart and checkout retry receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_unified_cart"
down_revision: str | None = "0016_order_delivery_pin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_table(
        "carts",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "cart_items",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("carts.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "canonical_id",
            sa.BigInteger(),
            sa.ForeignKey("canonical_products.id"),
            primary_key=True,
        ),
        sa.Column("qty", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit_code", sa.String(32), nullable=False),
        sa.CheckConstraint("qty > 0", name="positive_qty"),
    )
    op.create_table(
        "cart_merges",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("carts.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("merge_key", sa.String(160), primary_key=True),
    )
    op.create_table(
        "checkout_attempts",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("idempotency_key", sa.String(160), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("checkout_attempts")
    op.drop_table("cart_merges")
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_column("orders", "is_test")
