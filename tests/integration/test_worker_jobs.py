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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.ops import DailyMetrics
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.workers.tasks import (
    _abandon_baskets_impl,
    _admin_digest_impl,
    _mark_price_staleness_impl,
    _nudge_shops_impl,
    _recompute_trust_scores_impl,
    _rollup_metrics_impl,
)


class FakeBot:
    """Records Telegram sends instead of hitting the network."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


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
async def test_nudge_shops_sends_only_to_shops_with_aging_offers(
    test_session: AsyncSession,
) -> None:
    district = await _make_district(test_session)
    shop_aging = await _make_shop(test_session, district.id, owner_tg_id=111)
    shop_fresh = await _make_shop(test_session, district.id, owner_tg_id=222)
    now = datetime.now(UTC)

    test_session.add_all(
        [
            _make_offer(shop_aging.id, now - timedelta(days=6), staleness_state="aging"),
            _make_offer(shop_fresh.id, now - timedelta(days=1), staleness_state="fresh"),
        ]
    )
    await test_session.flush()

    bot = FakeBot()
    shops_count, sent = await _nudge_shops_impl(test_session, bot)  # type: ignore[arg-type]

    assert shops_count == 1
    assert sent == 1
    assert bot.sent[0][0] == 111


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

    assert "Eskirgan narxli do'konlar" in digest_text
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
