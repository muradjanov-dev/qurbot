"""Leased, per-order FIFO access to durable Telegram order notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models.order_workflow import OrderNotification

LEASE_DURATION = timedelta(minutes=2)
RETRY_DELAYS = (
    timedelta(seconds=30),
    timedelta(minutes=2),
    timedelta(minutes=10),
    timedelta(minutes=30),
)
MAX_ATTEMPTS = 1 + len(RETRY_DELAYS)


@dataclass(frozen=True, slots=True)
class ClaimedOrderNotification:
    id: int
    event_id: int
    order_id: int
    recipient_tg_id: int
    kind: str
    text: str
    payload: dict[str, object] | None
    attempts: int
    lease_token: str


def as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive timestamps and production UTC timestamps."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def claim_due_notifications(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 1,
) -> list[ClaimedOrderNotification]:
    """Lease FIFO heads due for delivery, committing leases before network I/O."""
    current = as_utc(now or datetime.now(UTC))
    earlier = aliased(OrderNotification)
    is_head = ~exists(
        select(1).where(
            earlier.order_id == OrderNotification.order_id,
            earlier.recipient_tg_id == OrderNotification.recipient_tg_id,
            earlier.id < OrderNotification.id,
            earlier.status != "sent",
        )
    )
    eligible = or_(
        and_(OrderNotification.status == "pending", OrderNotification.available_at <= current),
        and_(OrderNotification.status == "sending", OrderNotification.lease_until <= current),
    )
    rows = list(
        (
            await session.scalars(
                select(OrderNotification)
                .where(is_head, eligible)
                .order_by(OrderNotification.id)
                .limit(min(max(limit, 0), 100))
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    claims: list[ClaimedOrderNotification] = []
    for row in rows:
        token = str(uuid4())
        row.status = "sending"
        row.attempts += 1
        row.lease_until = current + LEASE_DURATION
        row.lease_token = token
        claims.append(
            ClaimedOrderNotification(
                id=row.id,
                event_id=row.event_id,
                order_id=row.order_id,
                recipient_tg_id=row.recipient_tg_id,
                kind=row.kind,
                text=row.text,
                payload=dict(row.payload) if row.payload else None,
                attempts=row.attempts,
                lease_token=token,
            )
        )
    await session.commit()
    return claims


async def mark_notification_sent(
    session: AsyncSession,
    claim: ClaimedOrderNotification,
    *,
    message_id: int,
    now: datetime | None = None,
) -> bool:
    """Complete only the lease that made the send; stale workers are fenced."""
    result = await session.execute(
        update(OrderNotification)
        .where(
            OrderNotification.id == claim.id,
            OrderNotification.status == "sending",
            OrderNotification.lease_token == claim.lease_token,
        )
        .values(
            status="sent",
            sent_at=as_utc(now or datetime.now(UTC)),
            telegram_message_id=message_id,
            lease_until=None,
            lease_token=None,
            last_error=None,
        )
    )
    await session.commit()
    return bool(result.rowcount)


async def mark_notification_failed(
    session: AsyncSession,
    claim: ClaimedOrderNotification,
    error: str,
    *,
    permanent: bool = False,
    retry_after: timedelta | None = None,
    now: datetime | None = None,
) -> bool:
    """Store a failure under its lease token, retaining a failed FIFO head."""
    current = as_utc(now or datetime.now(UTC))
    exhausted = claim.attempts >= MAX_ATTEMPTS
    failed = permanent or exhausted
    if retry_after is not None:
        delay = retry_after
    elif claim.attempts > 0 and claim.attempts <= len(RETRY_DELAYS):
        delay = RETRY_DELAYS[claim.attempts - 1]
    else:
        delay = timedelta(0)
    result = await session.execute(
        update(OrderNotification)
        .where(
            OrderNotification.id == claim.id,
            OrderNotification.status == "sending",
            OrderNotification.lease_token == claim.lease_token,
        )
        .values(
            status="failed" if failed else "pending",
            available_at=current + delay,
            lease_until=None,
            lease_token=None,
            last_error=error[:1000],
        )
    )
    await session.commit()
    return bool(result.rowcount)
