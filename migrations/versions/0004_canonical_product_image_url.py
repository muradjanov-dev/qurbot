"""Add canonical_products.image_url

Revision ID: 0004_canonical_product_image_url
Revises: 0003_phase9_hot_query_index
Create Date: 2026-08-13 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_canonical_product_image_url"
down_revision: str | None = "0003_phase9_hot_query_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "canonical_products", sa.Column("image_url", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("canonical_products", "image_url")
