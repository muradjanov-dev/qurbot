"""Order outbox delivery keeps per-recipient order, retries and leases safe."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_sales_postgres import pg_sessions as _pg_sessions

from app.core.config import settings
from app.db.models.order import Basket, Order, Quote
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.telegram_message import TelegramMessage
from app.db.models.user import User
from app.db.repositories.order_notification_repo import (
    RETRY_DELAYS,
    as_utc,
    claim_due_notifications,
    mark_notification_sent,
)
from app.services.order_notification_service import deliver_order_notifications

pg_sessions = _pg_sessions


class FakeBot:
    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.messages: list[tuple[int, str, dict[str, object]]] = []
        self.locations: list[tuple[int, float, float, int | None]] = []
        self.message_id = 100

    async def send_message(self, chat_id: int, text: str, **kwargs: object):
        if self.errors:
            raise self.errors.pop(0)
        self.message_id += 1
        self.messages.append((chat_id, text, kwargs))
        return SimpleNamespace(message_id=self.message_id)

    async def send_location(
        self,
        chat_id: int,
        *,
        latitude: float,
        longitude: float,
        reply_to_message_id: int | None = None,
    ):
        self.message_id += 1
        self.locations.append((chat_id, latitude, longitude, reply_to_message_id))
        return SimpleNamespace(message_id=self.message_id)


async def _base(session):
    customer = User(tg_id=77001, full_name="Customer", role="customer")
    admin = User(tg_id=77002, full_name="Admin", role="admin")
    session.add_all([customer, admin])
    await session.flush()
    basket = Basket(user_id=customer.id, raw_text="1 dona test", status="ordered")
    session.add(basket)
    await session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=100,
        delivery_total=0,
        grand_total=100,
        coverage_pct=100,
        shop_count=1,
    )
    session.add(quote)
    await session.flush()
    order = Order(
        quote_id=quote.id,
        user_id=customer.id,
        status="new",
        contact_phone="+998901234567",
        delivery_address="Test street",
        grand_total_quoted=100,
    )
    session.add(order)
    await session.flush()
    event = OrderEvent(
        order_id=order.id,
        actor_user_id=admin.id,
        kind="order_created",
        from_status=None,
        to_status="new",
        reason="",
        details={},
    )
    session.add(event)
    await session.flush()
    return customer, admin, order, event


async def _notification(
    session,
    *,
    order_id: int,
    event_id: int,
    recipient: int,
    kind: str = "customer_status",
    text: str = "<b>Order update</b>",
    payload: dict[str, object] | None = None,
    available_at: datetime | None = None,
) -> OrderNotification:
    row = OrderNotification(
        event_id=event_id,
        order_id=order_id,
        recipient_tg_id=recipient,
        kind=kind,
        text=text,
        payload=payload,
        status="pending",
        attempts=0,
        available_at=available_at or datetime.now(UTC) - timedelta(seconds=1),
    )
    session.add(row)
    await session.flush()
    return row


async def _event(session, *, order_id: int, actor_id: int, label: str) -> OrderEvent:
    row = OrderEvent(
        order_id=order_id,
        actor_user_id=actor_id,
        kind="status_changed",
        from_status="new",
        to_status="confirmed",
        reason=label,
        details={},
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_fifo_head_is_sent_before_later_order_updates(test_session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, admin, order, event = await _base(test_session)
    first = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=customer.tg_id,
        text="first",
    )
    second_event = await _event(test_session, order_id=order.id, actor_id=admin.id, label="second")
    second = await _notification(
        test_session,
        order_id=order.id,
        event_id=second_event.id,
        recipient=customer.tg_id,
        text="second",
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 1
    await test_session.refresh(first)
    await test_session.refresh(second)
    assert (first.status, second.status) == ("sent", "pending")
    assert [item[1] for item in bot.messages] == ["first"]

    assert await deliver_order_notifications(test_session, bot) == 1
    assert [item[1] for item in bot.messages] == ["first", "second"]


@pytest.mark.asyncio
async def test_failed_fifo_head_blocks_later_updates_until_manual_retry(test_session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, admin, order, event = await _base(test_session)
    first = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
        text="first",
    )
    second_event = await _event(
        test_session, order_id=order.id, actor_id=customer.id, label="second"
    )
    second = await _notification(
        test_session,
        order_id=order.id,
        event_id=second_event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
        text="second",
    )
    await test_session.commit()
    bot = FakeBot(TelegramForbiddenError(SendMessage(chat_id=admin.tg_id, text="first"), "blocked"))

    assert await deliver_order_notifications(test_session, bot) == 0
    await test_session.refresh(first)
    await test_session.refresh(second)
    assert first.status == "failed" and first.last_error == "telegram_forbidden"
    assert second.status == "pending"
    assert bot.messages == []

    # The core's authorized manual retry resets the failed head to pending.
    first.status = "pending"
    first.attempts = 0
    first.available_at = datetime.now(UTC) - timedelta(seconds=1)
    await test_session.commit()
    assert await deliver_order_notifications(test_session, bot) == 1
    assert [item[1] for item in bot.messages] == ["first"]
    await test_session.refresh(second)
    assert second.status == "pending"


@pytest.mark.asyncio
async def test_retry_after_is_honored_and_standard_backoff_exhausts_to_failed(
    test_session, monkeypatch
):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, admin, order, event = await _base(test_session)
    retry_after_row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=customer.tg_id,
    )
    await test_session.commit()
    now = datetime.now(UTC)
    bot = FakeBot(
        TelegramRetryAfter(
            SendMessage(chat_id=customer.tg_id, text="retry"), "rate limited", retry_after=90
        )
    )
    assert await deliver_order_notifications(test_session, bot, now=now) == 0
    await test_session.refresh(retry_after_row)
    assert retry_after_row.status == "pending" and retry_after_row.attempts == 1
    assert as_utc(retry_after_row.available_at) == now + timedelta(seconds=90)

    # Exercise the ordinary schedule independently of the RetryAfter override.
    retry_after_row.attempts = 0
    retry_after_row.available_at = now - timedelta(seconds=1)
    await test_session.commit()
    bot.errors = [RuntimeError("network") for _ in range(5)]
    row = retry_after_row
    now = datetime.now(UTC)
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        assert await deliver_order_notifications(test_session, bot, now=now) == 0
        await test_session.refresh(row)
        assert row.status == "pending" and row.attempts == attempt
        assert as_utc(row.available_at) == now + delay
        now = as_utc(row.available_at)
    assert await deliver_order_notifications(test_session, bot, now=now) == 0
    await test_session.refresh(row)
    assert row.status == "failed" and row.attempts == 5


@pytest.mark.asyncio
async def test_revoked_or_blocked_admin_is_failed_before_private_send(test_session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    monkeypatch.setattr(settings, "admin_tg_ids", [])
    monkeypatch.setattr(settings, "super_admin_tg_ids", [])
    customer, admin, order, event = await _base(test_session)
    admin.role = "customer"
    revoked = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
    )
    blocked_admin = User(tg_id=77003, full_name="Blocked admin", role="admin", is_blocked=True)
    test_session.add(blocked_admin)
    await test_session.flush()
    another_event = await _event(
        test_session, order_id=order.id, actor_id=customer.id, label="blocked"
    )
    blocked = await _notification(
        test_session,
        order_id=order.id,
        event_id=another_event.id,
        recipient=blocked_admin.tg_id,
        kind="admin_order_created",
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 0
    await test_session.refresh(revoked)
    await test_session.refresh(blocked)
    assert revoked.status == "failed" and revoked.last_error == "admin_role_revoked"
    assert blocked.status == "pending"
    assert await deliver_order_notifications(test_session, bot) == 0
    await test_session.refresh(blocked)
    assert blocked.status == "failed" and blocked.last_error == "recipient_blocked"
    assert bot.messages == []


@pytest.mark.asyncio
async def test_notifications_disabled_leaves_queue_pending_and_order_messages_never_cleanup(
    test_session, monkeypatch
):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", False)
    customer, admin, order, event = await _base(test_session)
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 0
    await test_session.refresh(row)
    assert row.status == "pending" and row.attempts == 0
    assert bot.messages == []
    assert await test_session.scalar(select(TelegramMessage.id)) is None


@pytest.mark.asyncio
async def test_stale_worker_cannot_complete_a_reclaimed_lease(test_session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, admin, order, event = await _base(test_session)
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=customer.tg_id,
    )
    await test_session.commit()
    claim = (await claim_due_notifications(test_session))[0]
    row.lease_token = "newer-owner"
    await test_session.commit()

    assert not await mark_notification_sent(test_session, claim, message_id=456)
    await test_session.refresh(row)
    assert row.status == "sending" and row.lease_token == "newer-owner"


@pytest.mark.asyncio
async def test_admin_location_follows_text_and_replies_to_its_telegram_message(
    test_session, monkeypatch
):
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, admin, order, event = await _base(test_session)
    text = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
        text="<b>Order</b>",
        payload={
            "reply_markup": {
                "inline_keyboard": [
                    [{"text": "Open order", "url": "https://shop.test/manage/orders/1"}]
                ]
            }
        },
    )
    location = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_location",
        payload={
            "latitude": 41.25,
            "longitude": 69.2,
            "reply_to_notification_id": text.id,
        },
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 1
    await test_session.refresh(location)
    assert location.status == "pending"
    sent_markup = bot.messages[0][2]["reply_markup"]
    assert sent_markup.inline_keyboard[0][0].url == "https://shop.test/manage/orders/1"

    assert await deliver_order_notifications(test_session, bot) == 1
    assert bot.locations == [(admin.tg_id, 41.25, 69.2, bot.messages[0][2].get("message_id", 101))]


@pytest.mark.asyncio
async def test_postgres_overlapping_claims_keep_fifo_and_fence_stale_worker(
    pg_sessions: async_sessionmaker[AsyncSession],
):
    async with pg_sessions() as session:
        customer, admin, order, event = await _base(session)
        first = await _notification(
            session,
            order_id=order.id,
            event_id=event.id,
            recipient=customer.tg_id,
            text="first",
        )
        second_event = await _event(session, order_id=order.id, actor_id=admin.id, label="second")
        second = await _notification(
            session,
            order_id=order.id,
            event_id=second_event.id,
            recipient=customer.tg_id,
            text="second",
        )
        await session.commit()
        first_id, second_id = first.id, second.id

    now = datetime.now(UTC)
    locked = asyncio.Event()
    release = asyncio.Event()

    async def hold_first_row_lock() -> None:
        async with pg_sessions() as session:
            await session.scalar(
                select(OrderNotification).where(OrderNotification.id == first_id).with_for_update()
            )
            locked.set()
            await release.wait()
            await session.rollback()

    lock_task = asyncio.create_task(hold_first_row_lock())
    try:
        await asyncio.wait_for(locked.wait(), timeout=5)
        async with pg_sessions() as session:
            assert await claim_due_notifications(session, now=now) == []
    finally:
        release.set()
        await lock_task

    async def claim_batch():
        async with pg_sessions() as session:
            return await claim_due_notifications(session, now=now)

    left, right = await asyncio.gather(claim_batch(), claim_batch())
    claimed = left or right
    assert len(claimed) == 1 and claimed[0].id == first_id
    assert not (left and right)

    async with pg_sessions() as session:
        reclaimed = await claim_due_notifications(session, now=now + timedelta(minutes=3))
        assert len(reclaimed) == 1 and reclaimed[0].id == first_id
        assert reclaimed[0].lease_token != claimed[0].lease_token
        assert not await mark_notification_sent(
            session, claimed[0], message_id=501, now=now + timedelta(minutes=3)
        )
        assert await mark_notification_sent(
            session, reclaimed[0], message_id=502, now=now + timedelta(minutes=3)
        )
        later = await claim_due_notifications(session, now=now + timedelta(minutes=3))
        assert [item.id for item in later] == [second_id]
