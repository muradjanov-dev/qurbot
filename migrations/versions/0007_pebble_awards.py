"""Pebble awards: the loyalty currency customers earn from orders

Revision ID: 0007_pebble_awards
Revises: 0006_shop_owners
Create Date: 2026-08-15 12:00:00.000000

Stored as a ledger rather than a balance column on users: the balance is the
sum of its rows, so it cannot drift from the events that produced it, and the
earning rules still to come (referrals, promotions, manual grants) are new
rows rather than a schema change.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_pebble_awards"
down_revision: str | None = "0006_shop_owners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pebble_awards",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pebble_awards_user_id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_pebble_awards_order_id"),
        sa.PrimaryKeyConstraint("id", name="pk_pebble_awards"),
        # Retrying a confirmation must not mint the same award twice.
        sa.UniqueConstraint("order_id", "source", name="uq_pebble_awards_order_source"),
    )
    op.create_index("ix_pebble_awards_user_id", "pebble_awards", ["user_id"])
    op.create_index("ix_pebble_awards_order_id", "pebble_awards", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_pebble_awards_order_id", table_name="pebble_awards")
    op.drop_index("ix_pebble_awards_user_id", table_name="pebble_awards")
    op.drop_table("pebble_awards")
