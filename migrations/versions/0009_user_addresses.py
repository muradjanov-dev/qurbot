"""Add user_addresses

Revision ID: 0009_user_addresses
Revises: 0008_draft_media_group
Create Date: 2026-08-16 10:00:00.000000

Customers save delivery places as pins rather than typed text. A street address
in Tashkent often does not resolve to a findable location, so the coordinates
are what the courier uses and the text is the label the customer confirmed on
top of them. Several per customer, because the right one depends on where the
delivery is going.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_user_addresses"
down_revision: str | None = "0008_draft_media_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_addresses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("lng", sa.Numeric(10, 7), nullable=False),
        sa.Column("address_text", sa.Text(), nullable=False),
        sa.Column("district_id", sa.BigInteger(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_addresses_user_id", "user_addresses", ["user_id"])
    op.create_index("ix_user_addresses_district_id", "user_addresses", ["district_id"])
    op.create_index("ix_user_addresses_user_default", "user_addresses", ["user_id", "is_default"])


def downgrade() -> None:
    op.drop_index("ix_user_addresses_user_default", table_name="user_addresses")
    op.drop_index("ix_user_addresses_district_id", table_name="user_addresses")
    op.drop_index("ix_user_addresses_user_id", table_name="user_addresses")
    op.drop_table("user_addresses")
