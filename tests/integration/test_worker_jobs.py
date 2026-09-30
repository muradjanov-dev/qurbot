"""Integration tests for Phase 8 scheduled jobs (SPEC §10).

Each job's `_*_impl` function is tested directly against the `test_session` fixture --
the arq-facing wrappers (`mark_price_staleness`, etc.) only add lock-acquire/commit
around these, using a separate module-level engine that isn't visible to the test's
in-memory sqlite session, so they aren't exercised here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.ops import DailyMetrics, Event
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.workers.tasks import (
    ORDER_REMINDER_EVENT,
    _abandon_baskets_impl,
    _admin_digest_impl,
    _mark_price_staleness_impl,
    _nudge_shops_impl,
    _recompute_trust_scores_impl,
    _remind_unconfirmed_orders_impl,
    _rollup_metrics_impl,
)


class FakeBot:
    """Records Telegram sends instead of hitting the network."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.markups: list[object | None] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))
        self.markups.append(kwargs.get("reply_markup"))


async def _make_district(session: AsyncSession) -> District:
    district = District(name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()
    return district


async def _make_shop(
    session: AsyncSession, district_id: int, owner_tg_id: int | None = None
) -> Shop:
    shop = Shop(
        name="Test Do'kon",
        phone="+998901234567",
        district_id=district_id,
        address="Test address",
        owner_tg_id=owner_tg_id,
    )
    session.add(shop)
    await session.flush()
    return shop


def _make_offer(shop_id: int, updated_at: datetime, staleness_state: str = "fresh") -> ShopProduct:
    return ShopProduct(
        shop_id=shop_id,
        raw_name="Sement M400",
        raw_unit="qop",
        price_per_pack=Decimal("55000.00"),
        price_per_base_unit=Decimal("1100.0000"),
        staleness_state=staleness_state,
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_mark_price_staleness(test_session: AsyncSession) -> None:
    district = await _make_district(test_session)
    shop = await _make_shop(test_session, district.id)
    now = datetime.now(UTC)

    fresh = _make_offer(shop.id, now - timedelta(days=1))
    aging = _make_offer(shop.id, now - timedelta(days=6))
    stale = _make_offer(shop.id, now - timedelta(days=8))
    test_session.add_all([fresh, aging, stale])
    await test_session.flush()

    aging_count, stale_count = await _mark_price_staleness_impl(test_session)
    assert aging_count == 1
    assert stale_count == 1

    await test_session.refresh(fresh)
    await test_session.refresh(aging)
    await test_session.refresh(stale)
    assert fresh.staleness_state == "fresh"
    assert aging.staleness_state == "aging"
    assert stale.staleness_state == "stale"

    # Idempotent: running again with the same data changes nothing further.
    aging_count_2, stale_count_2 = await _mark_price_staleness_impl(test_session)
    assert aging_count_2 == 0
    assert stale_count_2 == 0


@pytest.mark.asyncio
async def test_price_nudge_goes_to_the_admins_when_prices_age(
    test_session: AsyncSession,
) -> None:
    """Admins set every price, so they are the ones told -- never a shop owner id."""
    district = await _make_district(test_session)
    shop = await _make_shop(test_session, district.id, owner_tg_id=111)
    now = datetime.now(UTC)

    test_session.add_all(
        [
            _make_offer(shop.id, now - timedelta(days=6), staleness_state="aging"),
            _make_offer(shop.id, now - timedelta(days=1), staleness_state="fresh"),
        ]
    )
    await test_session.flush()

    bot = FakeBot()
    aging, sent = await _nudge_shops_impl(test_session, bot)  # type: ignore[arg-type]

    assert aging == 1
    assert sent == len(settings.admin_tg_ids)
    assert {chat_id for chat_id, _ in bot.sent} == set(settings.admin_tg_ids)


@pytest.mark.asyncio
async def test_price_nudge_is_silent_when_every_price_is_fresh(
    test_session: AsyncSession,
) -> None:
    district = await _make_district(test_session)
    shop = await _make_shop(test_session, district.id)
    test_session.add(_make_offer(shop.id, datetime.now(UTC), staleness_state="fresh"))
    await test_session.flush()

    bot = FakeBot()
    assert await _nudge_shops_impl(test_session, bot) == (0, 0)  # type: ignore[arg-type]
    assert bot.sent == []


@pytest.mark.asyncio
async def test_recompute_trust_scores(test_session: AsyncSession) -> None:
    district = await _make_district(test_session)
    shop = await _make_shop(test_session, district.id)
    shop.rating = Decimal("5.00")
    now = datetime.now(UTC)

    # 2 fresh, 1 stale -> freshness ratio 2/3
    test_session.add_all(
        [
            _make_offer(shop.id, now, staleness_state="fresh"),
            _make_offer(shop.id, now, staleness_state="fresh"),
            _make_offer(shop.id, now - timedelta(days=8), staleness_state="stale"),
        ]
    )
    await test_session.flush()

    updated = await _recompute_trust_scores_impl(test_session)
    assert updated == 1

    await test_session.refresh(shop)
    # No order history yet -> accept_rate defaults to 1.0 (benefit of the doubt).
    expected = (
        (Decimal(2) / Decimal(3)) * Decimal(str(settings.trust_score_freshness_weight))
        + Decimal("1") * Decimal(str(settings.trust_score_accept_rate_weight))
        + Decimal("1") * Decimal(str(settings.trust_score_rating_weight))
    ).quantize(Decimal("0.01"))
    assert shop.trust_score == expected


@pytest.mark.asyncio
async def test_rollup_metrics_writes_daily_metrics(test_session: AsyncSession) -> None:
    user = User(tg_id=555, lang="uz_latn")
    test_session.add(user)
    await test_session.flush()

    yesterday_start = datetime(2026, 8, 12, tzinfo=UTC)
    mid_day = yesterday_start + timedelta(hours=10)

    basket = Basket(user_id=user.id, raw_text="10 qop sement", status="ordered", created_at=mid_day)
    test_session.add(basket)
    await test_session.flush()

    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("100000.00"),
        delivery_total=Decimal("10000.00"),
        grand_total=Decimal("110000.00"),
        coverage_pct=Decimal("100.00"),
        shop_count=1,
        created_at=mid_day,
    )
    test_session.add(quote)
    await test_session.flush()

    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        contact_phone="+998901234567",
        delivery_address="Test address",
        grand_total_quoted=Decimal("110000.00"),
        created_at=mid_day,
    )
    test_session.add(order)
    await test_session.flush()

    record = await _rollup_metrics_impl(test_session, yesterday_start)

    assert record.date == yesterday_start.date()
    assert record.order_count == 1
    assert record.gmv == Decimal("110000.00")
    assert record.basket_count == 1

    # Idempotent re-run (same day) updates the same row rather than duplicating it.
    record_2 = await _rollup_metrics_impl(test_session, yesterday_start)
    assert record_2.id == record.id
    count_stmt = await test_session.execute(
        DailyMetrics.__table__.select().where(DailyMetrics.date == yesterday_start.date())
    )
    assert len(count_stmt.all()) == 1


@pytest.mark.asyncio
async def test_admin_digest_sends_to_all_admins(test_session: AsyncSession) -> None:
    district = await _make_district(test_session)
    shop = await _make_shop(test_session, district.id)
    now = datetime.now(UTC)
    test_session.add(_make_offer(shop.id, now - timedelta(days=8), staleness_state="stale"))
    await test_session.flush()

    bot = FakeBot()
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
    digest_text = await _admin_digest_impl(test_session, bot, day_start)  # type: ignore[arg-type]

    assert "Eskirgan narxlar: <b>1</b>" in digest_text
    assert len(bot.sent) == len(settings.admin_tg_ids)


@pytest.mark.asyncio
async def test_admin_digest_reports_ai_usage_against_the_limit(
    test_session: AsyncSession,
) -> None:
    """The budget is the one number in the digest that can silence the product.

    When it runs out every LLM stage stops answering and nothing announces it,
    so the daily report carries both what was spent and what is left.
    """
    spent = 12_000
    await OpsRepository(test_session).record_llm_call(
        purpose="batch_disambiguation",
        prompt_version="v1",
        input_hash="digest-usage",
        input_tokens=spent,
        output_tokens=0,
        cost_usd=Decimal("0.03"),
        latency_ms=10,
        cache_hit=False,
        raw_response="{}",
    )
    await test_session.flush()

    now = datetime.now(UTC)
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
    digest_text = await _admin_digest_impl(test_session, FakeBot(), day_start)  # type: ignore[arg-type]

    assert "AI sarfi" in digest_text
    assert f"{spent:,}" in digest_text
    assert "AI limitidan qolgani" in digest_text
    assert f"{settings.llm_daily_token_budget - spent:,}" in digest_text


@pytest.mark.asyncio
async def test_abandon_baskets(test_session: AsyncSession) -> None:
    user = User(tg_id=777, lang="uz_latn")
    test_session.add(user)
    await test_session.flush()

    now = datetime.now(UTC)
    old_basket = Basket(
        user_id=user.id,
        raw_text="10 qop sement",
        status="awaiting_confirmation",
        updated_at=now - timedelta(hours=25),
    )
    recent_basket = Basket(
        user_id=user.id,
        raw_text="5 dona gisht",
        status="awaiting_confirmation",
        updated_at=now - timedelta(hours=1),
    )
    test_session.add_all([old_basket, recent_basket])
    await test_session.flush()

    cutoff = now - timedelta(hours=settings.basket_abandon_hours)
    count = await _abandon_baskets_impl(test_session, cutoff)
    assert count == 1

    await test_session.refresh(old_basket)
    await test_session.refresh(recent_basket)
    assert old_basket.status == "abandoned"
    assert recent_basket.status == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_accept_rate_reflected_in_trust_score(test_session: AsyncSession) -> None:
    district = await _make_district(test_session)
    shop = await _make_shop(test_session, district.id)
    shop.rating = Decimal("5.00")
    now = datetime.now(UTC)
    test_session.add(_make_offer(shop.id, now, staleness_state="fresh"))

    user = User(tg_id=888, lang="uz_latn")
    test_session.add(user)
    await test_session.flush()

    basket = Basket(user_id=user.id, raw_text="x")
    test_session.add(basket)
    await test_session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("1"),
        delivery_total=Decimal("0"),
        grand_total=Decimal("1"),
        coverage_pct=Decimal("100"),
        shop_count=1,
    )
    test_session.add(quote)
    await test_session.flush()
    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        contact_phone="+998901234567",
        delivery_address="addr",
        grand_total_quoted=Decimal("1"),
    )
    test_session.add(order)
    await test_session.flush()

    # 1 accepted, 1 rejected -> accept_rate 0.5
    test_session.add_all(
        [
            OrderShopPart(
                order_id=order.id, shop_id=shop.id, subtotal=Decimal("1"), shop_response="accepted"
            ),
            OrderShopPart(
                order_id=order.id, shop_id=shop.id, subtotal=Decimal("1"), shop_response="rejected"
            ),
            OrderShopPart(
                order_id=order.id, shop_id=shop.id, subtotal=Decimal("1"), shop_response="pending"
            ),
        ]
    )
    await test_session.flush()

    await _recompute_trust_scores_impl(test_session)
    await test_session.refresh(shop)

    expected = (
        Decimal("1") * Decimal(str(settings.trust_score_freshness_weight))
        + Decimal("0.5") * Decimal(str(settings.trust_score_accept_rate_weight))
        + Decimal("1") * Decimal(str(settings.trust_score_rating_weight))
    ).quantize(Decimal("0.01"))
    assert shop.trust_score == expected


async def _placed_but_unconfirmed(session: AsyncSession, minutes_ago: int) -> Order:
    """An order in the state it is created in, aged by `minutes_ago`."""
    user = User(tg_id=987654, lang="uz_latn", full_name="Mijoz")
    session.add(user)
    await session.flush()
    basket = Basket(user_id=user.id, raw_text="10 dona fanera", status="ordered")
    session.add(basket)
    await session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("100000"),
        delivery_total=Decimal("0"),
        grand_total=Decimal("100000"),
        coverage_pct=Decimal("100"),
        shop_count=1,
    )
    session.add(quote)
    await session.flush()
    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        status="new",
        contact_phone="+998901234567",
        delivery_address="Chilonzor 9",
        grand_total_quoted=Decimal("100000"),
    )
    session.add(order)
    await session.flush()
    await session.execute(
        Order.__table__.update()
        .where(Order.id == order.id)
        .values(created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago))
    )
    await session.flush()
    await session.refresh(order)
    return order


@pytest.mark.asyncio
async def test_an_order_left_unconfirmed_reminds_the_admins(test_session: AsyncSession) -> None:
    """The customer has already been told it is placed; the silence is on our side."""
    order = await _placed_but_unconfirmed(test_session, minutes_ago=15)
    order.workflow_revision = 7
    admin_id = settings.admin_tg_ids[0]
    admin = await test_session.scalar(select(User).where(User.tg_id == admin_id))
    if admin is None:
        test_session.add(User(tg_id=admin_id, role="admin", lang="ru"))
    else:
        admin.lang = "ru"
    await test_session.commit()
    bot = FakeBot()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 1
    assert len(bot.sent) == len(settings.admin_tg_ids)
    assert f"#{order.id}" in bot.sent[0][1]
    buttons = [button for row in bot.markups[0].inline_keyboard for button in row]
    assert buttons[0].text == "✅ Подтвердить заказ"
    assert buttons[0].callback_data == f"admin_order:confirm:{order.id}:7"
    assert buttons[1].text == "❌ Отменить заказ"
    assert buttons[1].url.endswith(f"/manage/orders/{order.id}")
    assert buttons[1].callback_data is None


@pytest.mark.asyncio
async def test_order_reminder_escapes_customer_phone_and_address(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = 900905
    monkeypatch.setattr(settings, "admin_tg_ids", [admin_id])
    monkeypatch.setattr(
        settings, "test_tg_ids", [tg_id for tg_id in settings.test_tg_ids if tg_id != admin_id]
    )
    test_session.add(User(tg_id=admin_id, role="admin", lang="uz_latn"))
    order = await _placed_but_unconfirmed(test_session, minutes_ago=15)
    order.contact_phone = "<b>Phone</b> & gate"
    order.delivery_address = "<b>Customer text</b> & gate"
    await test_session.commit()
    bot = FakeBot()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 1
    reminder = bot.sent[0][1]
    assert "Tel: &lt;b&gt;Phone&lt;/b&gt; &amp; gate" in reminder
    assert "Manzil: &lt;b&gt;Customer text&lt;/b&gt; &amp; gate" in reminder
    assert "<b>Customer text</b>" not in reminder
    assert "<b>100 000 so'm</b>" in reminder


@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [
        (
            "uz_latn",
            "⏰ <b>Buyurtma #{order_id} hali tasdiqlanmagan</b>\n\n"
            "120 daqiqadan beri kutmoqda.\n"
            "Summa: <b>100 000 so'm</b>\n"
            "📞 Tel: +998901234567\n"
            "📍 Manzil: Chilonzor 9\n\n"
            "Iltimos, mijozga qo'ng'iroq qilib tasdiqlang.",
        ),
        (
            "uz_cyrl",
            "⏰ <b>Буюртма #{order_id} ҳали тасдиқланмаган</b>\n\n"
            "120 дақиқадан бери кутмоқда.\n"
            "Сумма: <b>100 000 сўм</b>\n"
            "📞 Тел: +998901234567\n"
            "📍 Манзил: Chilonzor 9\n\n"
            "Илтимос, мижозга қўнғироқ қилиб тасдиқланг.",
        ),
        (
            "ru",
            "⏰ <b>Заказ #{order_id} ещё не подтверждён</b>\n\n"
            "Ожидает подтверждения уже 120 мин.\n"
            "Сумма: <b>100 000 сум</b>\n"
            "📞 Телефон: +998901234567\n"
            "📍 Адрес: Chilonzor 9\n\n"
            "Пожалуйста, позвоните клиенту и подтвердите заказ.",
        ),
    ],
)
@pytest.mark.asyncio
async def test_order_reminder_translates_the_complete_message(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    lang: str,
    expected_text: str,
) -> None:
    admin_id = 900902
    monkeypatch.setattr(settings, "admin_tg_ids", [admin_id])
    monkeypatch.setattr(
        settings, "test_tg_ids", [tg_id for tg_id in settings.test_tg_ids if tg_id != admin_id]
    )
    test_session.add(User(tg_id=admin_id, role="admin", lang=lang))
    order = await _placed_but_unconfirmed(test_session, minutes_ago=120)
    await test_session.commit()
    bot = FakeBot()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 1
    assert bot.sent == [(admin_id, expected_text.format(order_id=order.id))]


@pytest.mark.parametrize("unavailable_reason", ["blocked", "test_user", "test_id"])
@pytest.mark.asyncio
async def test_reminder_waits_for_an_eligible_admin_before_marking_order(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    unavailable_reason: str,
) -> None:
    await _placed_but_unconfirmed(test_session, minutes_ago=15)
    admin_ids = list(dict.fromkeys(settings.admin_tg_ids))
    assert admin_ids
    admin_users = {
        user.tg_id: user
        for user in (
            await test_session.scalars(select(User).where(User.tg_id.in_(admin_ids)))
        ).all()
        if user.tg_id is not None
    }
    for admin_id in admin_ids:
        admin = admin_users.get(admin_id)
        if admin is None:
            admin = User(tg_id=admin_id, role="admin", lang="ru")
            test_session.add(admin)
            admin_users[admin_id] = admin
        if unavailable_reason == "blocked":
            admin.is_blocked = True
        elif unavailable_reason == "test_user":
            admin.is_test = True

    original_test_ids = list(settings.test_tg_ids)
    if unavailable_reason == "test_id":
        monkeypatch.setattr(settings, "test_tg_ids", list(set(original_test_ids) | set(admin_ids)))
    await test_session.commit()

    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)
    bot = FakeBot()
    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 0
    assert bot.sent == []
    assert (
        await test_session.scalar(select(Event.id).where(Event.name == ORDER_REMINDER_EVENT))
        is None
    )

    eligible_id = admin_ids[0]
    eligible = admin_users[eligible_id]
    eligible.is_blocked = False
    eligible.is_test = False
    eligible.role = "customer"  # Configured IDs remain authoritative without a role row.
    monkeypatch.setattr(
        settings,
        "test_tg_ids",
        [tg_id for tg_id in settings.test_tg_ids if tg_id != eligible_id],
    )
    await test_session.commit()

    later_bot = FakeBot()
    later_sent = await _remind_unconfirmed_orders_impl(test_session, later_bot, cutoff)  # type: ignore[arg-type]

    assert later_sent == 1
    assert [chat_id for chat_id, _text in later_bot.sent] == [eligible_id]
    assert (
        await test_session.scalar(select(Event.id).where(Event.name == ORDER_REMINDER_EVENT))
        is not None
    )


@pytest.mark.asyncio
async def test_configured_admin_without_user_row_receives_reminder(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = 900903
    monkeypatch.setattr(settings, "admin_tg_ids", [admin_id])
    monkeypatch.setattr(
        settings, "test_tg_ids", [tg_id for tg_id in settings.test_tg_ids if tg_id != admin_id]
    )
    await _placed_but_unconfirmed(test_session, minutes_ago=15)
    assert await test_session.scalar(select(User).where(User.tg_id == admin_id)) is None
    bot = FakeBot()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 1
    assert [chat_id for chat_id, _text in bot.sent] == [admin_id]
    assert (
        await test_session.scalar(select(Event.id).where(Event.name == ORDER_REMINDER_EVENT))
        is not None
    )
    assert await test_session.scalar(select(User).where(User.tg_id == admin_id)) is None


@pytest.mark.asyncio
async def test_failed_reminder_send_does_not_mark_order_as_reminded(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = 900904
    monkeypatch.setattr(settings, "admin_tg_ids", [admin_id])
    monkeypatch.setattr(
        settings, "test_tg_ids", [tg_id for tg_id in settings.test_tg_ids if tg_id != admin_id]
    )
    test_session.add(User(tg_id=admin_id, role="admin"))
    await _placed_but_unconfirmed(test_session, minutes_ago=15)
    await test_session.flush()

    class FailingBot(FakeBot):
        async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
            raise TelegramForbiddenError(SendMessage(chat_id=chat_id, text=text), "blocked")

    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)
    failed_sent = await _remind_unconfirmed_orders_impl(
        test_session,
        FailingBot(),
        cutoff,  # type: ignore[arg-type]
    )

    assert failed_sent == 0
    assert (
        await test_session.scalar(select(Event.id).where(Event.name == ORDER_REMINDER_EVENT))
        is None
    )

    later_bot = FakeBot()
    later_sent = await _remind_unconfirmed_orders_impl(
        test_session,
        later_bot,
        cutoff,  # type: ignore[arg-type]
    )

    assert later_sent == 1
    assert [chat_id for chat_id, _text in later_bot.sent] == [admin_id]
    assert (
        await test_session.scalar(select(Event.id).where(Event.name == ORDER_REMINDER_EVENT))
        is not None
    )


@pytest.mark.asyncio
async def test_reminder_rechecks_admin_revocation_before_each_order(
    test_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_id = 900901
    monkeypatch.setattr(settings, "admin_tg_ids", [admin_id])
    monkeypatch.setattr(
        settings, "test_tg_ids", [tg_id for tg_id in settings.test_tg_ids if tg_id != admin_id]
    )
    admin = User(tg_id=admin_id, role="admin")
    test_session.add(admin)
    first = await _placed_but_unconfirmed(test_session, minutes_ago=30)
    second = Order(
        quote_id=first.quote_id,
        user_id=first.user_id,
        status="new",
        contact_phone="+998900000002",
        delivery_address="Second private address",
        grand_total_quoted=first.grand_total_quoted,
        created_at=first.created_at,
    )
    test_session.add(second)
    await test_session.flush()

    class RevokingBot(FakeBot):
        async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
            await super().send_message(chat_id, text, **kwargs)
            if len(self.sent) == 1:
                await test_session.execute(
                    User.__table__.update().where(User.tg_id == admin_id).values(is_blocked=True)
                )
                assert not admin.is_blocked  # Core update leaves the identity map stale.

    bot = RevokingBot()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 1
    assert [chat_id for chat_id, _text in bot.sent] == [admin_id]
    assert "Second private address" not in bot.sent[0][1]
    reminded_order_ids = {
        props["order_id"]
        for (props,) in (
            await test_session.execute(
                select(Event.props).where(Event.name == ORDER_REMINDER_EVENT)
            )
        ).all()
    }
    assert reminded_order_ids == {first.id}


@pytest.mark.asyncio
async def test_a_fresh_order_is_left_alone(test_session: AsyncSession) -> None:
    await _placed_but_unconfirmed(test_session, minutes_ago=2)
    bot = FakeBot()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    sent = await _remind_unconfirmed_orders_impl(test_session, bot, cutoff)  # type: ignore[arg-type]

    assert sent == 0
    assert bot.sent == []


@pytest.mark.asyncio
async def test_the_reminder_is_said_once_not_every_five_minutes(
    test_session: AsyncSession,
) -> None:
    """Repeating it each run would train the admins to ignore it."""
    await _placed_but_unconfirmed(test_session, minutes_ago=30)
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.order_confirm_reminder_minutes)

    first = await _remind_unconfirmed_orders_impl(test_session, FakeBot(), cutoff)  # type: ignore[arg-type]
    second = await _remind_unconfirmed_orders_impl(test_session, FakeBot(), cutoff)  # type: ignore[arg-type]

    assert first == 1
    assert second == 0
