"""Manual sales enquiries and durable Telegram progress indicators."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021_sales_requests"
down_revision = "0020_test_customers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("district_id", sa.BigInteger(), sa.ForeignKey("districts.id"), nullable=False),
        sa.Column("district_name", sa.String(300), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_by", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_sales_requests_user_id"),
    )
    for column in ("user_id", "conversation_id", "status"):
        op.create_index("ix_sales_requests_" + column, "sales_requests", [column])
    op.create_table(
        "sales_request_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "request_id", sa.BigInteger(), sa.ForeignKey("sales_requests.id"), nullable=False
        ),
        sa.Column(
            "canonical_id", sa.BigInteger(), sa.ForeignKey("canonical_products.id"), nullable=False
        ),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("attributes", JSONB(), nullable=False),
        sa.Column("qty", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit_code", sa.String(32), nullable=False),
        sa.Column("reference_unit_price", sa.Numeric(14, 2)),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_sales_request_items_request_id", "sales_request_items", ["request_id"])
    op.add_column("conversation_jobs", sa.Column("telegram_status_id", sa.BigInteger()))
    op.add_column(
        "conversation_jobs",
        sa.Column("progress_slot", sa.Integer(), nullable=False, server_default="-1"),
    )
    op.add_column(
        "conversation_jobs", sa.Column("progress_lease_until", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    raise RuntimeError(
        "Keep customer enquiries and progress receipts when rolling back application code"
    )
