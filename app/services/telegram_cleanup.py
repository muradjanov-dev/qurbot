"""Explicit registration and durable 24-hour cleanup of transient Telegram messages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.telegram_message import TelegramMessage
from app.db.models.user import User
from app.db.session import async_session_factory
from app.workers.locks import try_acquire_job_lock

logger = logging.getLogger(__name__)

TRANSIENT_MESSAGE_TYPES = frozenset(
    {
        "ai_customer_inbound",
        "ai_customer_outbound",
        "ai_customer_status",
        "guided_sales_transient",
    }
)
MESSAGE_RETENTION = timedelta(hours=24)
TELEGRAM_DELETE_LIMIT = 100
TELEGRAM_DELETE_WINDOW = timedelta(hours=48)
DELETE_LEASE = timedelta(minutes=2)
MAX_RETRY_ATTEMPTS = 8


def _as_utc(value: datetime) -> datetime:
    """Normalize DB-returned naive SQLite datetimes and aware production values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def register_transient_message(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    message_type: str,
    sent_at: datetime | None = None,
) -> None:
    """Register a known transient AI/guided chat message for deletion at +24h.

    Call only for customer AI chat, AI status/progress, or guided variant/cart
    transient messages. This allowlist intentionally has no admin, order,
    checkout, receipt, or generic message type.
    """
    if message_type not in TRANSIENT_MESSAGE_TYPES:
        raise ValueError(f"Unsupported transient Telegram message type: {message_type}")
    if (
        isinstance(chat_id, bool)
        or not isinstance(chat_id, int)
        or chat_id <= 0
        or isinstance(message_id, bool)
        or not isinstance(message_id, int)
        or message_id <= 0
    ):
        raise ValueError("Transient messages require positive private chat and message ids")

    sent = sent_at or datetime.now(UTC)
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=UTC)
    sent = _as_utc(sent)
    due = sent + MESSAGE_RETENTION

    # Protect configured admins and dynamically promoted admin accounts even
    # if a caller accidentally queues one of their private-chat messages.
    if (
        chat_id in settings.admin_tg_ids
        or chat_id in settings.super_admin_tg_ids
        or await session.scalar(select(User.id).where(User.tg_id == chat_id, User.role == "admin"))
    ):
        return

    values = {
        "chat_id": chat_id,
        "message_id": message_id,
        "message_type": message_type,
        "sent_at": sent,
        "due_at": due,
        "status": "pending",
        "attempt_count": 0,
        "next_attempt_at": due,
    }
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement_pg = postgres_insert(TelegramMessage).values(**values)
        await session.execute(
            statement_pg.on_conflict_do_nothing(index_elements=["chat_id", "message_id"])
        )
    elif dialect_name == "sqlite":
        statement_sqlite = sqlite_insert(TelegramMessage).values(**values)
        await session.execute(
            statement_sqlite.on_conflict_do_nothing(index_elements=["chat_id", "message_id"])
        )
    else:
        # The production and test dialects support conflict-safe inserts. Keep
        # a fallback for other local database adapters.
        existing = await session.scalar(
            select(TelegramMessage).where(
                TelegramMessage.chat_id == chat_id,
                TelegramMessage.message_id == message_id,
            )
        )
        if existing is None:
            session.add(TelegramMessage(**values))


async def mark_transient_message_deleted(
    session: AsyncSession,
    *,
    chat_id: int,
    message_id: int,
    deleted_at: datetime | None = None,
) -> None:
    """Mark a message deleted after a caller successfully removes it."""
    row = await session.scalar(
        select(TelegramMessage).where(
            TelegramMessage.chat_id == chat_id,
            TelegramMessage.message_id == message_id,
        )
    )
    if row is None:
        return
    if row.status != "deleted":
        row.status = "deleted"
        row.deleted_at = _as_utc(deleted_at or datetime.now(UTC))
        row.lease_until = None
        row.last_error = None


def queue_transient_message(
    data: dict[str, Any],
    *,
    chat_id: int,
    message_id: int,
    message_type: str,
    sent_at: datetime | None = None,
) -> None:
    """Queue an explicit registration for ``TelegramCleanupMiddleware``.

    Handlers may instead call ``register_transient_message`` directly using
    the injected session. Queued rows are persisted after the handler returns.
    """
    if message_type not in TRANSIENT_MESSAGE_TYPES:
        raise ValueError(f"Unsupported transient Telegram message type: {message_type}")
    if (
        isinstance(chat_id, bool)
        or not isinstance(chat_id, int)
        or chat_id <= 0
        or isinstance(message_id, bool)
        or not isinstance(message_id, int)
        or message_id <= 0
    ):
        raise ValueError("Transient messages require positive private chat and message ids")
    queue = data.setdefault("telegram_cleanup_messages", [])
    queue.append((chat_id, message_id, message_type, sent_at))


async def _claim_due_messages(
    session: AsyncSession, *, now: datetime, limit: int
) -> list[TelegramMessage]:
    rows = list(
        (
            await session.scalars(
                select(TelegramMessage)
                .where(
                    TelegramMessage.due_at <= now,
                    TelegramMessage.next_attempt_at <= now,
                    or_(
                        TelegramMessage.status.in_(("pending", "retry")),
                        (TelegramMessage.status == "deleting")
                        & (TelegramMessage.lease_until <= now),
                    ),
                )
                .order_by(TelegramMessage.due_at, TelegramMessage.id)
                .limit(min(max(limit, 0), TELEGRAM_DELETE_LIMIT))
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for row in rows:
        row.status = "deleting"
        row.lease_until = now + DELETE_LEASE
    await session.flush()
    await session.commit()
    return rows


async def _admin_chat_ids(session: AsyncSession, chat_ids: set[int]) -> set[int]:
    if not chat_ids:
        return set()
    registered = await session.scalars(
        select(User.tg_id).where(User.role == "admin", User.tg_id.in_(chat_ids))
    )
    return {tg_id for tg_id in registered.all() if tg_id is not None}


def _retry_at(now: datetime, attempt: int, retry_after: int | None = None) -> datetime:
    if retry_after is not None:
        return now + timedelta(seconds=max(1, retry_after))
    return now + timedelta(seconds=min(6 * 60 * 60, 30 * (2 ** min(attempt - 1, 9))))


async def _cleanup_telegram_messages_impl(
    session: AsyncSession,
    bot: Bot,
    *,
    now: datetime | None = None,
    batch_size: int = TELEGRAM_DELETE_LIMIT,
) -> tuple[int, int, int]:
    """Delete one bounded batch; returns (deleted, retried, terminal)."""
    clock_now = _as_utc(now or datetime.now(UTC))
    rows = await _claim_due_messages(session, now=clock_now, limit=batch_size)
    deleted = retried = terminal = 0
    protected_chats = set(settings.admin_tg_ids) | set(settings.super_admin_tg_ids)
    protected_chats |= await _admin_chat_ids(session, {row.chat_id for row in rows})

    for row in rows:
        if row.chat_id in protected_chats:
            row.status = "protected"
            row.last_error = "admin_chat_protected"
            row.lease_until = None
            terminal += 1
            await session.commit()
            continue
        # Telegram rejects deleteMessage at 48h. A long outage must converge
        # to a terminal row instead of retrying an impossible request forever.
        if clock_now - _as_utc(row.sent_at) >= TELEGRAM_DELETE_WINDOW:
            row.status = "expired"
            row.last_error = "telegram_delete_window_expired"
            row.lease_until = None
            terminal += 1
            await session.commit()
            continue

        try:
            await bot.delete_message(chat_id=row.chat_id, message_id=row.message_id)
        except TelegramBadRequest as exc:
            # “Message to delete not found” means it was already removed; all
            # other BadRequest failures are permanent (including protected or
            # inaccessible messages) and should not be retried indefinitely.
            if "message to delete not found" in str(exc).lower():
                row.status = "deleted"
                row.deleted_at = clock_now
                row.last_error = None
                deleted += 1
            else:
                row.status = "failed"
                row.last_error = str(exc)[:160]
                terminal += 1
            row.lease_until = None
            await session.commit()
        except (TelegramRetryAfter, TelegramNetworkError, TelegramServerError) as exc:
            row.attempt_count += 1
            row.last_error = type(exc).__name__
            row.lease_until = None
            if row.attempt_count >= MAX_RETRY_ATTEMPTS:
                row.status = "failed"
                terminal += 1
            else:
                row.status = "retry"
                delay = exc.retry_after if isinstance(exc, TelegramRetryAfter) else None
                row.next_attempt_at = _retry_at(clock_now, row.attempt_count, delay)
                retried += 1
            await session.commit()
        except TelegramAPIError as exc:
            row.status = "failed"
            row.last_error = (str(exc) or type(exc).__name__)[:160]
            row.lease_until = None
            terminal += 1
            await session.commit()
        except Exception as exc:
            # Unknown transport/client errors get a bounded retry policy too.
            row.attempt_count += 1
            row.last_error = type(exc).__name__
            row.lease_until = None
            if row.attempt_count >= MAX_RETRY_ATTEMPTS:
                row.status = "failed"
                terminal += 1
            else:
                row.status = "retry"
                row.next_attempt_at = _retry_at(clock_now, row.attempt_count)
                retried += 1
            await session.commit()
            logger.warning(
                "telegram_cleanup_delete_error",
                extra={"message_id": row.message_id},
                exc_info=True,
            )
        else:
            row.status = "deleted"
            row.deleted_at = clock_now
            row.last_error = None
            row.lease_until = None
            deleted += 1
            await session.commit()

    return deleted, retried, terminal


async def cleanup_telegram_messages(ctx: dict[str, Any]) -> None:
    """Worker entrypoint: delete due registered transient messages every 5m."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "cleanup_telegram_messages"):
            logger.info("job_skipped_locked", extra={"job": "cleanup_telegram_messages"})
            return
        bot = ctx.get("bot")
        if bot is None:
            logger.warning("telegram_cleanup_bot_missing")
            return
        deleted, retried, terminal = await _cleanup_telegram_messages_impl(session, bot)
        logger.info(
            "telegram_cleanup_done",
            extra={"deleted": deleted, "retried": retried, "terminal": terminal},
        )
