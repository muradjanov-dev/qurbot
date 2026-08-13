"""Phase 8: daily_metrics rollup table

Revision ID: 0002_phase8_ops
Revises: 0001_initial_schema
Create Date: 2026-08-13 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_phase8_ops"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("gmv", sa.Numeric(precision=16, scale=2), nullable=False, server_default="0.00"),
        sa.Column("order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("basket_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "match_rate", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0.00"
        ),
        sa.Column(
            "auto_match_rate",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "avg_lines_per_basket",
            sa.Numeric(precision=6, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "quote_to_order_rate",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "price_freshness_pct",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "llm_cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column(
            "strategy_mix",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_daily_metrics"),
        sa.UniqueConstraint("date", name="uq_daily_metrics_date"),
    )
    op.create_index("ix_daily_metrics_date", "daily_metrics", ["date"])


def downgrade() -> None:
    op.drop_table("daily_metrics")
