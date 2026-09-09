"""Set the current public delivery price policy.

Revision ID: 0013_delivery_policy
Revises: 0012_price_tiers
Create Date: 2026-09-09 13:00:00.000000

All existing rules must quote the same policy customers were promised:
50,000 UZS through 5,000,000 UZS, and free strictly above that amount.
The strict comparison lives in the domain calculation; this migration makes
the existing production rows use its fee and threshold.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_delivery_policy"
down_revision: str | None = "0012_price_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_delivery_rules = sa.table(
    "shop_delivery_rules",
    sa.column("fee", sa.Numeric(14, 2)),
    sa.column("free_above", sa.Numeric(14, 2)),
)


def upgrade() -> None:
    op.get_bind().execute(
        _delivery_rules.update().values(
            fee=sa.literal(50000),
            free_above=sa.literal(5000000),
        )
    )


def downgrade() -> None:
    # The former rows contained several independently configured values, so a
    # downgrade cannot reconstruct them without inventing business data.
    pass
