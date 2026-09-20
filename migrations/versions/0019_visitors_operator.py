"""Anonymous customer sessions and operator inbox read state.

Revision ID: 0019_visitors_operator
Revises: 0018_conversations
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_visitors_operator"
down_revision = "0018_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "tg_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("orders", sa.Column("contact_name", sa.String(100), nullable=True))
    op.create_table(
        "visitor_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_visitor_sessions_user_id", "visitor_sessions", ["user_id"])
    op.create_index("ix_visitor_sessions_expires_at", "visitor_sessions", ["expires_at"])
    op.add_column(
        "conversations",
        sa.Column("last_customer_channel", sa.String(16), server_default="web", nullable=False),
    )
    op.execute("""UPDATE conversations c SET last_customer_channel = COALESCE(
        (SELECT m.channel FROM conversation_messages m WHERE m.conversation_id=c.id
         AND m.role='user' ORDER BY m.sequence DESC LIMIT 1), 'web')""")
    op.create_table(
        "conversation_reads",
        sa.Column(
            "conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), primary_key=True
        ),
        sa.Column("admin_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    # Restoring NOT NULL with real guest orders would destroy their ownership.
    # Roll back application images to a guest-aware release, not customer data.
    raise RuntimeError("Data-preserving migration: use a guest-compatible application rollback")
