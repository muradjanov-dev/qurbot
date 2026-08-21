"""Retire the seeded demo shops and their synthetic offers

Revision ID: 0010_retire_seeded_market
Revises: 0009_user_addresses
Create Date: 2026-08-16 12:00:00.000000

The seed dataset creates 20 placeholder shops carrying roughly 4,000 offers
whose prices are generated as ``50000 * random(0.92..1.15)`` regardless of what
the product is. That was fine as dev fixture data, but in production it meant
customers were being quoted prices that mean nothing -- a real order was placed
against one of these shops.

This deactivates them rather than deleting them, for two reasons:

* ``order_items.shop_product_id`` is NOT NULL, so deleting an offer that
  already appears in an order would violate the foreign key and take the
  order history with it.
* Deactivating is reversible -- ``downgrade`` puts them straight back, which
  matters if a shop here turns out to be one someone actually onboarded.

Shops are matched by name because nothing else distinguishes them: the seed
leaves ``shop_products.updated_by`` at its ``'shop'`` default, which is exactly
what the owner upload wizard writes, so that column cannot tell them apart.
The names are inlined rather than imported from scripts/seed.py so this
migration keeps describing the same rows even as the seed changes.

Deploys run ``scripts/seed.py --catalog-only``, which stops before shops and
offers, so they do not come back.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_retire_seeded_market"
down_revision: str | None = "0009_user_addresses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEEDED_SHOP_NAMES = (
    "Baraka Qurilish",
    "Nur Stroy Yunusobod",
    "O'rikzor Mega Stroy",
    "Mirzo Ulug'bek Qurilish Markazi",
    "Yakkasaroy Master Stroy",
    "Jomboy Savdo Markazi",
    "Olmazor Temir va Sement",
    "Sergeli Qurilish Bozori 7-do'kon",
    "Mirobod Elite Stroy",
    "Yashnobod Qurilish Baza",
    "Bektemir Metal Trade",
    "Uchtepa Kafel & Plitka",
    "Akfa & Knauf Rasmiy Dileri",
    "Ideal Sement Chilonzor",
    "StroyMarket Yunusobod",
    "Toshkent Santexnika Markazi",
    "Grand Bo'yoq va Lak",
    "Quruvchi Do'st Sergeli",
    "Keles Stroy Baza",
    "Toshkent Viloyat Stroy Terminal",
)


# Minimal table definitions: a migration must keep working even after the ORM
# models it mirrors have moved on.
_shops = sa.table("shops", sa.column("id"), sa.column("name"), sa.column("is_active"))
_shop_products = sa.table("shop_products", sa.column("shop_id"), sa.column("is_active"))


def set_seeded_market_active(connection: sa.engine.Connection, active: bool) -> tuple[int, int]:
    """Flip is_active on the seeded shops and their offers. Returns (offers, shops)."""
    names = list(SEEDED_SHOP_NAMES)
    seeded_ids = sa.select(_shops.c.id).where(_shops.c.name.in_(names))

    offers = connection.execute(
        _shop_products.update()
        .where(_shop_products.c.shop_id.in_(seeded_ids))
        .values(is_active=active)
    )
    shops = connection.execute(
        _shops.update().where(_shops.c.name.in_(names)).values(is_active=active)
    )
    return offers.rowcount, shops.rowcount


def _set_active(active: bool) -> None:
    offer_count, shop_count = set_seeded_market_active(op.get_bind(), active)
    print(
        f"[0010] is_active={active}: {offer_count} offers, {shop_count} shops",
        flush=True,
    )


def upgrade() -> None:
    _set_active(False)


def downgrade() -> None:
    _set_active(True)
