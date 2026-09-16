"""One shop: retire every partner shop and the shop-owner role

Revision ID: 0015_single_house_shop
Revises: 0014_llm_call_observability
Create Date: 2026-09-14 12:00:00.000000

QurBot stops being a marketplace. Every price is ours, sold from a single shop
row named "QurBot", and only admins manage it. This revision makes the
database agree:

* every other shop, and every offer it carries, is deactivated, so no partner
  price can reach a quote;
* accounts holding the ``shop_owner`` role go back to ``customer`` -- there is
  no longer anything for that role to open.

Deactivated, never deleted: ``order_items.shop_product_id`` and
``order_shop_parts.shop_id`` point at these rows, and order history has to keep
resolving. ``shop_owners`` is left in place for the same reason -- it is the
record of who ran which shop.

The house shop is matched by name, inlined here rather than read from
settings, so this migration keeps describing the same rows even if the setting
later moves.

Downgrade is a no-op on purpose. Which shops were active before, and which
users were owners, is not recoverable from the post-upgrade state; guessing
would reactivate the seeded demo market that 0010 retired. The rows are all
still there if something has to be restored by hand.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_single_house_shop"
down_revision: str | None = "0014_llm_call_observability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


HOUSE_SHOP_NAME = "QurBot"

_shops = sa.table("shops", sa.column("id"), sa.column("name"), sa.column("is_active"))
_shop_products = sa.table("shop_products", sa.column("shop_id"), sa.column("is_active"))
_users = sa.table("users", sa.column("role"))


def retire_partner_shops(connection: sa.engine.Connection) -> tuple[int, int, int]:
    """Deactivate every shop but ours, and its offers. Returns (offers, shops, users)."""
    partner_ids = sa.select(_shops.c.id).where(_shops.c.name != HOUSE_SHOP_NAME)

    offers = connection.execute(
        _shop_products.update()
        .where(
            _shop_products.c.shop_id.in_(partner_ids),
            _shop_products.c.is_active.is_(True),
        )
        .values(is_active=False)
    )
    shops = connection.execute(
        _shops.update()
        .where(_shops.c.name != HOUSE_SHOP_NAME, _shops.c.is_active.is_(True))
        .values(is_active=False)
    )
    users = connection.execute(
        _users.update().where(_users.c.role == "shop_owner").values(role="customer")
    )
    return offers.rowcount, shops.rowcount, users.rowcount


def upgrade() -> None:
    offers, shops, users = retire_partner_shops(op.get_bind())
    print(
        f"[0015] retired {shops} partner shops, {offers} offers; {users} shop owners -> customer",
        flush=True,
    )


def downgrade() -> None:
    pass
