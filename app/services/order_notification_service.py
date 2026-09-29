"""Deliver order workflow outbox rows to verified Telegram recipients.

The database lease prevents ordinary worker overlap, while a token fence keeps
late workers from changing a row after its lease has been reclaimed. Telegram
does not accept idempotency keys, so a timeout after Telegram accepted a send
can still produce a duplicate when the lease is retried.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardMarkup
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import get_admin_order_decision_keyboard
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.order import Order
from app.db.models.order_workflow import OrderNotification
from app.db.models.user import User
from app.db.repositories.order_notification_repo import (
    ClaimedOrderNotification,
    claim_due_notifications,
    mark_notification_failed,
    mark_notification_sent,
)

logger = get_logger(__name__)

ADMIN_NOTIFICATION_KINDS = frozenset({"admin_order_created", "admin_order_location"})
CUSTOMER_NOTIFICATION_KINDS = frozenset(
    {
        "customer_order_ack",
        "customer_status",
        "customer_status_correction",
        "customer_courier_contact",
    }
)


def _permanent_error(exc: Exception) -> tuple[str, bool, timedelta | None]:
    if isinstance(exc, TelegramRetryAfter):
        raw = getattr(exc, "retry_after", 0)
        seconds = float(raw.total_seconds()) if hasattr(raw, "total_seconds") else float(raw)
        return "telegram_retry_after", False, timedelta(seconds=max(0.0, seconds))
    if isinstance(exc, TelegramForbiddenError):
        return "telegram_forbidden", True, None
    if isinstance(exc, TelegramNotFound):
        return "telegram_chat_not_found", True, None
    if isinstance(exc, TelegramBadRequest):
        return "telegram_bad_request", True, None
    if isinstance(exc, TelegramNetworkError | TelegramServerError | TelegramAPIError):
        return "telegram_transient_error", False, None
    return "notification_send_error", False, None


async def _current_user_for_tg(session: AsyncSession, tg_id: int) -> User | None:
    return await session.scalar(
        select(User).where(User.tg_id == tg_id).execution_options(populate_existing=True)
    )


async def _recipient_error(
    session: AsyncSession,
    claim: ClaimedOrderNotification,
) -> str | None:
    """Recheck current recipient ownership before any private message send."""
    recipient = await _current_user_for_tg(session, claim.recipient_tg_id)
    if claim.recipient_tg_id in settings.test_tg_ids or (
        recipient is not None and recipient.is_test
    ):
        return "test_recipient"
    if recipient is not None and recipient.is_blocked:
        return "recipient_blocked"

    if claim.kind in ADMIN_NOTIFICATION_KINDS:
        configured = set(settings.admin_tg_ids)
        if (recipient is not None and recipient.role == "admin") or (
            claim.recipient_tg_id in configured
        ):
            return None
        return "admin_role_revoked"

    if claim.kind not in CUSTOMER_NOTIFICATION_KINDS:
        return "unsupported_notification_kind"

    order = await session.get(Order, claim.order_id)
    owner = await session.get(User, order.user_id) if order is not None else None
    if owner is None or owner.tg_id != claim.recipient_tg_id:
        return "customer_recipient_mismatch"
    if owner.is_blocked:
        return "recipient_blocked"
    return None


def _reply_markup(payload: dict[str, object] | None) -> InlineKeyboardMarkup | None:
    if not payload:
        return None
    raw = payload.get("reply_markup")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("invalid_reply_markup")
    try:
        return InlineKeyboardMarkup.model_validate(raw)
    except ValidationError as exc:
        raise ValueError("invalid_reply_markup") from exc


async def _related_admin_message_id(
    session: AsyncSession,
    claim: ClaimedOrderNotification,
) -> int | None:
    payload = claim.payload or {}
    raw_id = payload.get("reply_to_notification_id")
    if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id <= 0:
        return None
    parent = await session.scalar(
        select(OrderNotification).where(
            OrderNotification.id == raw_id,
            OrderNotification.order_id == claim.order_id,
            OrderNotification.recipient_tg_id == claim.recipient_tg_id,
            OrderNotification.kind == "admin_order_created",
            OrderNotification.status == "sent",
        )
    )
    return parent.telegram_message_id if parent is not None else None


async def _send_claim(
    session: AsyncSession,
    bot: Bot,
    claim: ClaimedOrderNotification,
) -> int:
    error = await _recipient_error(session, claim)
    if error is not None:
        raise _PermanentDeliveryError(error)

    if claim.kind == "admin_order_location":
        payload = claim.payload or {}
        latitude, longitude = payload.get("latitude"), payload.get("longitude")
        if (
            isinstance(latitude, bool)
            or isinstance(longitude, bool)
            or not isinstance(latitude, int | float)
            or not isinstance(longitude, int | float)
            or not math.isfinite(float(latitude))
            or not math.isfinite(float(longitude))
            or not -90 <= float(latitude) <= 90
            or not -180 <= float(longitude) <= 180
        ):
            raise _PermanentDeliveryError("invalid_location_payload")
        reply_to = await _related_admin_message_id(session, claim)
        if reply_to is None:
            raise _PermanentDeliveryError("admin_order_message_not_sent")
        message = await bot.send_location(
            chat_id=claim.recipient_tg_id,
            latitude=float(latitude),
            longitude=float(longitude),
            reply_to_message_id=reply_to,
        )
        return int(message.message_id)

    kwargs: dict[str, Any] = {"parse_mode": ParseMode.HTML}
    if claim.kind == "admin_order_created":
        try:
            markup = _reply_markup(claim.payload)
        except ValueError as exc:
            raise _PermanentDeliveryError(str(exc)) from exc
        kwargs["reply_markup"] = markup or get_admin_order_decision_keyboard(claim.order_id)
    message = await bot.send_message(
        chat_id=claim.recipient_tg_id,
        text=claim.text,
        **kwargs,
    )
    return int(message.message_id)


class _PermanentDeliveryError(Exception):
    """A row that cannot succeed without changing its recipient or payload."""


async def deliver_order_notifications(
    session: AsyncSession,
    bot: Bot,
    *,
    now: datetime | None = None,
    limit: int = 1,
) -> int:
    """Deliver one batch of ready order events; return the successful sends."""
    # A disabled integration must leave durable rows pending for a later
    # re-enable; it must not claim, skip, or falsely mark them delivered.
    if not settings.telegram_notifications_enabled:
        return 0

    current = now or datetime.now(UTC)
    claimed = await claim_due_notifications(session, now=current, limit=limit)
    delivered = 0
    for claim in claimed:
        try:
            message_id = await _send_claim(session, bot, claim)
        except _PermanentDeliveryError as exc:
            await mark_notification_failed(session, claim, str(exc), permanent=True, now=current)
            logger.warning(
                "order_notification_suppressed",
                notification_id=claim.id,
                order_id=claim.order_id,
                kind=claim.kind,
                reason=str(exc),
            )
        except Exception as exc:
            label, permanent, retry_after = _permanent_error(exc)
            await mark_notification_failed(
                session,
                claim,
                label,
                permanent=permanent,
                retry_after=retry_after,
                now=current,
            )
            logger.warning(
                "order_notification_send_failed",
                notification_id=claim.id,
                order_id=claim.order_id,
                kind=claim.kind,
                reason=label,
            )
        else:
            if await mark_notification_sent(session, claim, message_id=message_id, now=current):
                delivered += 1
            else:
                # Telegram may already have accepted this send, but another
                # worker reclaimed its lease before this result was recorded.
                logger.warning(
                    "order_notification_lease_lost_after_send",
                    notification_id=claim.id,
                    order_id=claim.order_id,
                    kind=claim.kind,
                )
    return delivered
