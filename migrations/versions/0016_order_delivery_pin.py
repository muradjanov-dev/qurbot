"""Store the delivery pin on the order

Revision ID: 0016_order_delivery_pin
Revises: 0015_single_house_shop
Create Date: 2026-09-14 15:00:00.000000

Admins were told where an order goes only as text, and a typed Tashkent
address frequently does not resolve to a findable place. The customer already
confirms a pin at checkout; copying it onto the order lets the admin
notification carry a Telegram location the courier can open directly.

Nullable: a customer on Telegram Desktop can only type an address, and orders
placed before this revision have no pin to backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_order_delivery_pin"
down_revision: str | None = "0015_single_house_shop"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("orders", sa.Column("delivery_lng", sa.Numeric(10, 7), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "delivery_lng")
    op.drop_column("orders", "delivery_lat")
