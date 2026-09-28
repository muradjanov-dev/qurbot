"""Stop tracking numeric offer quantities.

Revision ID: 0024_unlimited_stock
Revises: 0023_default_lang_cyrillic
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_unlimited_stock"
down_revision: str | None = "0023_default_lang_cyrillic"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE shop_products SET stock_qty = NULL WHERE stock_qty IS NOT NULL")


def downgrade() -> None:
    # Quantity data is intentionally discarded by the upgrade and cannot be restored.
    pass
