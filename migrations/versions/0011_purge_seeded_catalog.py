"""Record where a product came from, and delete the system-seeded catalogue

Revision ID: 0011_purge_seeded_catalog
Revises: 0010_retire_seeded_market
Create Date: 2026-08-22 10:00:00.000000

Two changes that only make sense together.

First, ``canonical_products`` gains provenance. Until now nothing distinguished
a product the seed script invented from one transcribed off a real supplier's
price list -- the admin catalogue screen showed 222 rows with no price and no
way to tell which were real. ``source`` answers "who added this", ``source_ref``
names the specific supplier, and ``reference_price`` carries that supplier's
list price so the catalogue is worth showing before any shop has uploaded a
live offer. ``reference_price`` is NULL when the price list says "Kelishiladi"
-- negotiable is not the same as zero, and a zero would quietly win every
optimiser comparison.

Second, the seeded catalogue goes. Migration 0010 deactivated the seeded shops
and their synthetic offers; what was left behind was 222 products with nothing
behind them, which is what an operator sees when they open the catalogue. Every
row that exists when this migration runs predates the ``source`` column, so the
``'seed'`` server default correctly labels all of them.

Unlike 0010 this deletes rather than deactivates, which was an explicit call --
these rows are noise, not history. The one thing that cannot be deleted is a
product some real order was placed against: ``order_items.canonical_id`` is NOT
NULL, so deleting it would take the order history with it. Those products are
kept and reported; every other reference (basket_lines, shop_products,
import_rows, shop_product_drafts, unmatched_queries) is nullable and is nulled
out first.

``downgrade`` drops the three columns. It cannot bring the deleted products
back -- ``scripts/seed.py`` is what re-creates a catalogue.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_purge_seeded_catalog"
down_revision: str | None = "0010_retire_seeded_market"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Minimal table definitions: a migration must keep working even after the ORM
# models it mirrors have moved on.
_products = sa.table(
    "canonical_products",
    sa.column("id"),
    sa.column("source"),
)
_aliases = sa.table("product_aliases", sa.column("canonical_id"))
_order_items = sa.table("order_items", sa.column("canonical_id"))

# Every other table pointing at a product does so nullably, so the reference
# can be released instead of blocking the delete. The column is named
# differently in each -- an import row records what it *matched*, an unmatched
# query records what was *suggested* -- so both halves are listed here.
_NULLABLE_REFERENCES = (
    ("basket_lines", "canonical_id"),
    ("shop_products", "canonical_id"),
    ("import_rows", "matched_canonical_id"),
    ("shop_product_drafts", "matched_canonical_id"),
    ("unmatched_queries", "suggested_canonical_id"),
)


def purge_seeded_catalog(connection: sa.engine.Connection) -> tuple[int, int, int]:
    """Delete every ``source='seed'`` product not referenced by an order.

    Returns ``(products_deleted, aliases_deleted, products_kept)``, where the
    kept ones are those an order was placed against.
    """
    ordered = sa.select(_order_items.c.canonical_id)

    doomed_ids = [
        row[0]
        for row in connection.execute(
            sa.select(_products.c.id).where(
                _products.c.source == "seed",
                _products.c.id.notin_(ordered),
            )
        )
    ]
    kept = int(
        connection.execute(
            sa.select(sa.func.count())
            .select_from(_products)
            .where(_products.c.source == "seed", _products.c.id.in_(ordered))
        ).scalar()
        or 0
    )

    if not doomed_ids:
        return 0, 0, kept

    for table_name, column_name in _NULLABLE_REFERENCES:
        table = sa.table(table_name, sa.column(column_name))
        connection.execute(
            table.update().where(table.c[column_name].in_(doomed_ids)).values({column_name: None})
        )

    aliases = connection.execute(
        _aliases.delete().where(_aliases.c.canonical_id.in_(doomed_ids))
    ).rowcount
    products = connection.execute(_products.delete().where(_products.c.id.in_(doomed_ids))).rowcount
    return products, aliases, kept


def upgrade() -> None:
    op.add_column(
        "canonical_products",
        sa.Column("source", sa.String(length=32), nullable=False, server_default="seed"),
    )
    op.add_column(
        "canonical_products",
        sa.Column("source_ref", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "canonical_products",
        sa.Column("reference_price", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.create_index("ix_canonical_products_source", "canonical_products", ["source"])

    products, aliases, kept = purge_seeded_catalog(op.get_bind())
    print(
        f"[0011] purged seeded catalogue: {products} products, {aliases} aliases, "
        f"{kept} kept (referenced by orders)",
        flush=True,
    )


def downgrade() -> None:
    op.drop_index("ix_canonical_products_source", table_name="canonical_products")
    op.drop_column("canonical_products", "reference_price")
    op.drop_column("canonical_products", "source_ref")
    op.drop_column("canonical_products", "source")
