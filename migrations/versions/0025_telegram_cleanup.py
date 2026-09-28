"""Track explicitly selected transient Telegram messages for 24h cleanup."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_telegram_cleanup"
down_revision: str | None = "0024_unlimited_stock"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_type", sa.String(length=40), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=160), nullable=True),
        sa.UniqueConstraint("chat_id", "message_id", name="uq_telegram_messages_chat_id"),
    )
    op.create_index("ix_telegram_messages_due_at", "telegram_messages", ["due_at"])
    op.create_index("ix_telegram_messages_status", "telegram_messages", ["status"])


def downgrade() -> None:
    op.drop_index("ix_telegram_messages_status", table_name="telegram_messages")
    op.drop_index("ix_telegram_messages_due_at", table_name="telegram_messages")
    op.drop_table("telegram_messages")
