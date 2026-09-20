"""Durable shared chat, ordered requests, and a notification outbox."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import PK_BIGINT, Base, TimestampMixin
from app.db.models.shop import JSONType


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="ai", index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    last_customer_channel: Mapped[str] = mapped_column(
        String(16), default="web", server_default="web"
    )
    generation: Mapped[int] = mapped_column(Integer, default=0)
    next_sequence: Mapped[int] = mapped_column(Integer, default=0)
    agent_state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationRead(Base):
    __tablename__ = "conversation_reads"
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)


class ConversationMessage(Base, TimestampMixin):
    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence"),)

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    cards: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)


class ConversationJob(Base, TimestampMixin):
    __tablename__ = "conversation_jobs"
    __table_args__ = (UniqueConstraint("conversation_id", "request_id"),)

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("conversation_messages.id"))
    request_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    response_id: Mapped[int | None] = mapped_column(ForeignKey("conversation_messages.id"))
    error: Mapped[str | None] = mapped_column(String(64))
    tool_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)


class ConversationNotification(Base, TimestampMixin):
    __tablename__ = "conversation_notifications"
    __table_args__ = (UniqueConstraint("event_key", "tg_id"),)

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(128))
    tg_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    kind: Mapped[str] = mapped_column(String(24))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
