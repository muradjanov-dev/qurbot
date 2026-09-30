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
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.shop import District
from app.db.models.telegram_message import TelegramMessage
from app.db.models.user import User
from app.db.repositories.order_notification_repo import (
    MAX_ATTEMPTS,
    RETRY_DELAYS,
    as_utc,
    claim_due_notifications,
    mark_notification_sent,
)
from app.services.house_shop import get_house_shop
from app.services.order_notification_service import deliver_order_notifications
from app.services.order_workflow import OrderWorkflowService

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


class ControlledClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class AdvancingFakeBot(FakeBot):
    def __init__(self, clock: ControlledClock, elapsed: timedelta, *errors: Exception) -> None:
        super().__init__(*errors)
        self.clock = clock
        self.elapsed = elapsed

    async def send_message(self, chat_id: int, text: str, **kwargs: object):
        self.clock.advance(self.elapsed)
        return await super().send_message(chat_id, text, **kwargs)


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
async def test_normal_delivery_flow_sends_departure_and_following_delivery_status(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, admin, order, _event_row = await _base(test_session)
    customer.lang = "ru"
    test_session.add(District(name_uz="Test", name_ru="Test"))
    await test_session.flush()
    house = await get_house_shop(test_session)
    assert house is not None
    test_session.add(
        OrderShopPart(order_id=order.id, shop_id=house.id, subtotal=100, delivery_fee=0)
    )
    await test_session.flush()
    service = OrderWorkflowService(test_session)
    await service.change_status(order.id, admin, "confirmed", 0)
    await service.change_status(order.id, admin, "collecting", 1)
    await service.update_courier(order.id, admin, "Audit Courier", "+998901112233", "Van", None, 2)
    await service.change_status(order.id, admin, "in_transit", 3)
    await service.change_status(order.id, admin, "fulfilled", 4)
    await test_session.commit()

    bot = FakeBot()
    sent_count = 0
    for _ in range(4):
        sent_count += await deliver_order_notifications(test_session, bot)

    assert sent_count == 4
    assert [recipient for recipient, _text, _kwargs in bot.messages] == [customer.tg_id] * 4
    assert "Audit Courier" in bot.messages[2][1]
    assert "+998901112233" in bot.messages[2][1]
    assert "Van" in bot.messages[2][1]
    rows = (
        await test_session.scalars(select(OrderNotification).order_by(OrderNotification.id))
    ).all()
    notification_statuses = (
        await test_session.execute(
            select(OrderNotification.kind, OrderEvent.to_status)
            .join(OrderEvent, OrderEvent.id == OrderNotification.event_id)
            .order_by(OrderNotification.id)
        )
    ).all()
    assert notification_statuses == [
        ("customer_status", "confirmed"),
        ("customer_status", "collecting"),
        ("customer_departure", "in_transit"),
        ("customer_status", "fulfilled"),
    ]
    assert [row.status for row in rows] == ["sent"] * 4
    assert bot.messages[3][1] == (f"📦 Статус заказа <b>#{order.id}</b>: <b>Доставлен</b>.")


@pytest.mark.asyncio
async def test_unknown_customer_notification_is_not_sent(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, _admin, order, event = await _base(test_session)
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=customer.tg_id,
        kind="unknown_customer_notification",
    )
    await test_session.commit()
    bot = FakeBot()
    assert await deliver_order_notifications(test_session, bot) == 0
    await test_session.refresh(row)
    assert row.status == "failed"
    assert row.last_error == "unsupported_notification_kind"
    assert bot.messages == []


@pytest.mark.parametrize(
    ("error", "retry_delay"),
    [
        pytest.param(
            TelegramRetryAfter(
                SendMessage(chat_id=77001, text="retry"), "rate limited", retry_after=1
            ),
            timedelta(seconds=1),
            id="telegram-retry-after",
        ),
        pytest.param(RuntimeError("network"), timedelta(seconds=30), id="transient-error"),
    ],
)
@pytest.mark.asyncio
async def test_retry_delay_starts_when_failed_send_returns(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    retry_delay: timedelta,
) -> None:
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    customer, _admin, order, event = await _base(test_session)
    started_at = datetime.now(UTC)
    send_elapsed = timedelta(seconds=20)
    clock = ControlledClock(started_at)
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=customer.tg_id,
        available_at=started_at - timedelta(seconds=1),
    )
    await test_session.commit()

    bot = AdvancingFakeBot(clock, send_elapsed, error)
    await deliver_order_notifications(test_session, bot, now=started_at, clock=clock)

    await test_session.refresh(row)
    assert as_utc(row.available_at) == started_at + send_elapsed + retry_delay


@pytest.mark.asyncio
async def test_expired_fifth_lease_becomes_failed_without_a_sixth_send(test_session) -> None:
    customer, admin, order, event = await _base(test_session)
    first = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=customer.tg_id,
    )
    next_event = await _event(test_session, order_id=order.id, actor_id=admin.id, label="next")
    await _notification(
        test_session,
        order_id=order.id,
        event_id=next_event.id,
        recipient=customer.tg_id,
    )
    now = datetime.now(UTC)
    first.status = "sending"
    first.attempts = MAX_ATTEMPTS
    first.lease_token = "expired-fifth-attempt"
    first.lease_until = now - timedelta(seconds=1)
    await test_session.commit()

    assert await claim_due_notifications(test_session, now=now) == []
    await test_session.refresh(first)
    assert first.status == "failed"
    assert first.attempts == MAX_ATTEMPTS
    assert first.last_error == "lease_expired_attempts_exhausted"
    # A failed FIFO head cannot let the later status reach Telegram out of order.
    assert await claim_due_notifications(test_session, now=now + timedelta(hours=1)) == []


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
async def test_missing_admin_keyboard_uses_current_revision_and_recipient_language(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    monkeypatch.setattr(settings, "webhook_base_url", "https://shop.test")
    monkeypatch.setattr(settings, "storefront_webapp_url", None)
    _customer, admin, order, event = await _base(test_session)
    admin.lang = "ru"
    order.workflow_revision = 7
    test_session.add(District(name_uz="Test", name_ru="Test"))
    await test_session.flush()
    house = await get_house_shop(test_session)
    assert house is not None
    test_session.add(
        OrderShopPart(order_id=order.id, shop_id=house.id, subtotal=100, delivery_fee=0)
    )
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
        payload=None,
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 1

    await test_session.refresh(row)
    markup = bot.messages[0][2]["reply_markup"]
    confirm, cancel = markup.inline_keyboard[0]
    assert row.status == "sent"
    assert confirm.text == "✅ Подтвердить заказ"
    assert confirm.callback_data == f"admin_order:confirm:{order.id}:7"
    assert cancel.text == "❌ Отменить заказ"
    assert cancel.url.endswith(f"/manage/orders/{order.id}")


@pytest.mark.asyncio
async def test_missing_admin_keyboard_does_not_confirm_an_order_past_new(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    monkeypatch.setattr(settings, "webhook_base_url", "https://shop.test")
    monkeypatch.setattr(settings, "storefront_webapp_url", None)
    _customer, admin, order, event = await _base(test_session)
    admin.lang = "uz_cyrl"
    order.status = "confirmed"
    order.workflow_revision = 2
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
        payload=None,
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 1

    await test_session.refresh(row)
    assert row.status == "sent"
    markup = bot.messages[0][2]["reply_markup"]
    assert len(markup.inline_keyboard) == 1
    open_order = markup.inline_keyboard[0][0]
    assert open_order.text == "Буюртмани очиш"
    assert open_order.url.endswith(f"/manage/orders/{order.id}")
    assert open_order.callback_data is None


@pytest.mark.asyncio
async def test_malformed_admin_keyboard_still_permanently_fails(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_notifications_enabled", True)
    _customer, admin, order, event = await _base(test_session)
    row = await _notification(
        test_session,
        order_id=order.id,
        event_id=event.id,
        recipient=admin.tg_id,
        kind="admin_order_created",
        payload={"reply_markup": "not-a-keyboard"},
    )
    await test_session.commit()
    bot = FakeBot()

    assert await deliver_order_notifications(test_session, bot) == 0

    await test_session.refresh(row)
    assert row.status == "failed"
    assert row.last_error == "invalid_reply_markup"
    assert bot.messages == []


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
