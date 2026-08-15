"""Add shop_product_drafts.media_group_id

Revision ID: 0008_draft_media_group
Revises: 0007_pebble_awards
Create Date: 2026-08-15 12:00:00.000000

Telegram delivers a photo album as several separate updates that share a
media_group_id, and only the first carries the caption. Storing it lets the
later photos find the draft the first one created, so album handling needs no
in-memory buffering and survives a restart mid-album.

Kept as its own revision rather than folded into 0005, which is already applied.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_draft_media_group"
down_revision: str | None = "0007_pebble_awards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shop_product_drafts",
        sa.Column("media_group_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_shop_product_drafts_media_group_id", "shop_product_drafts", ["media_group_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_shop_product_drafts_media_group_id", table_name="shop_product_drafts")
    op.drop_column("shop_product_drafts", "media_group_id")
