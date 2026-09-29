"""Add the auditable single-house order delivery workflow and notification outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_order_delivery_workflow"
down_revision: str | None = "0026_currency_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("workflow_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("orders", sa.Column("courier_name", sa.String(length=120), nullable=True))
    op.add_column("orders", sa.Column("courier_phone", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("courier_vehicle", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("courier_cost_uzs", sa.Numeric(14, 2), nullable=True))
    op.add_column("orders", sa.Column("delivery_note", sa.Text(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("delivery_problem", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "order_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_events")),
    )
    op.create_index("ix_order_events_order_created", "order_events", ["order_id", "created_at"])

    op.create_table(
        "order_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("order_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recipient_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_notifications")),
        sa.UniqueConstraint(
            "event_id", "recipient_tg_id", "kind", name="uq_order_notifications_event_recipient"
        ),
    )
    op.create_index(
        "ix_order_notifications_status_available",
        "order_notifications",
        ["status", "available_at"],
    )
    op.create_index("ix_order_notifications_order_id", "order_notifications", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_notifications_order_id", table_name="order_notifications")
    op.drop_index("ix_order_notifications_status_available", table_name="order_notifications")
    op.drop_table("order_notifications")
    op.drop_index("ix_order_events_order_created", table_name="order_events")
    op.drop_table("order_events")
    op.drop_column("orders", "delivery_problem")
    op.drop_column("orders", "delivery_note")
    op.drop_column("orders", "courier_cost_uzs")
    op.drop_column("orders", "courier_vehicle")
    op.drop_column("orders", "courier_phone")
    op.drop_column("orders", "courier_name")
    op.drop_column("orders", "workflow_revision")
