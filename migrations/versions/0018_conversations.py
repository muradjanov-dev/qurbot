"""Shared conversations and recoverable AI requests.

Revision ID: 0018_conversations
Revises: 0017_unified_cart
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_conversations"
down_revision = "0017_unified_cart"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False, unique=True
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("operator_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("agent_state", postgresql.JSONB(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("cards", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("conversation_id", "sequence"),
        *timestamps(),
    )
    op.create_index(
        "ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"]
    )
    op.create_table(
        "conversation_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column(
            "message_id", sa.BigInteger(), sa.ForeignKey("conversation_messages.id"), nullable=False
        ),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("response_id", sa.BigInteger(), sa.ForeignKey("conversation_messages.id")),
        sa.Column("error", sa.String(64)),
        sa.Column("tool_results", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("conversation_id", "request_id"),
        *timestamps(),
    )
    op.create_index(
        "ix_conversation_jobs_conversation_id", "conversation_jobs", ["conversation_id"]
    )
    op.create_index("ix_conversation_jobs_status", "conversation_jobs", ["status"])
    op.create_table(
        "conversation_notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "conversation_id", sa.BigInteger(), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.UniqueConstraint("event_key", "tg_id"),
        *timestamps(),
    )


def downgrade() -> None:
    for table in (
        "conversation_notifications",
        "conversation_jobs",
        "conversation_messages",
        "conversations",
    ):
        op.drop_table(table)
