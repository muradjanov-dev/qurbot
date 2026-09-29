"""The FX singleton must isolate quote/order reads from rate publication."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select
from test_sales_postgres import pg_sessions as _pg_sessions
from test_sales_postgres import seed

from app.core.config import settings
from app.db.models import User
from app.db.models.order import Order, Quote
from app.db.models.shop import District, Shop, ShopDeliveryRule, ShopProduct, ShopProductPriceTier
from app.services.fx_pricing import FxConflict, FxPricingService
from app.services.order_service import place_order
from app.web.storefront.quoting import optimize, validate_lines

pg_sessions = _pg_sessions


async def _priced_fixture(factory):
    user_id, product_id, admins = await seed(factory)
    async with factory() as session:
        district = District(region="Test", name_uz="Test", name_ru="Test")
        session.add(district)
        await session.flush()
        shop = Shop(
            name=settings.house_shop_name,
            phone="+998900000000",
            district_id=district.id,
            address="Isolated test",
        )
        session.add(shop)
        await session.flush()
        fx = FxPricingService(session)
        await fx.publish_rate(Decimal("10"), admins[0])
        offer = ShopProduct(
            shop_id=shop.id,
            canonical_id=product_id,
            raw_name="Test",
            raw_unit="dona",
            pack_unit_code="dona",
            pack_size=Decimal("1"),
            stock_status="in_stock",
            staleness_state="fresh",
        )
        await fx.set_offer_price(offer, Decimal("7"), "USD", "dona")
        tier = ShopProductPriceTier(shop_product_id=offer.id, min_qty=Decimal("2"))
        await fx.set_tier_price(tier, Decimal("6"), "USD")
        session.add(
            ShopDeliveryRule(
                shop_id=shop.id,
                district_id=district.id,
                fee=Decimal("0"),
                min_order=Decimal("0"),
                eta_hours=24,
            )
        )
        await session.commit()
        return user_id, product_id, admins, district.id, offer.id


async def _quote(session, product_id, district_id):
    basket = await validate_lines(
        session, [{"canonical_id": product_id, "qty": "2", "unit_code": "dona"}]
    )
    variants = await optimize(session, basket.items, district_id=district_id)
    assert variants and variants[0].is_orderable
    return variants[0]


@pytest.mark.asyncio
async def test_quote_and_confirmed_order_hold_one_rate_while_publisher_waits(pg_sessions):
    user_id, product_id, admins, district_id, _ = await _priced_fixture(pg_sessions)
    started = asyncio.Event()

    async def publish():
        async with pg_sessions() as session:
            started.set()
            await FxPricingService(session).publish_rate(Decimal("20"), admins[0], 1)
            await session.commit()

    async with pg_sessions() as reader:
        snapshot = await FxPricingService(reader).snapshot(lock=True)
        assert snapshot.revision == 1
        task = asyncio.create_task(publish())
        try:
            await started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.1)
            variant = await _quote(reader, product_id, district_id)
            assert variant.items_total_uzs == Decimal("120")
            user = await reader.get(User, user_id)
            placed = await place_order(
                reader,
                user=user,
                variant=variant,
                contact_phone="+998900000000",
                delivery_address="Isolated test",
            )
            order_id = placed.order.id
            await reader.commit()
            await asyncio.wait_for(task, 5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with pg_sessions() as session:
        new_quote = await _quote(session, product_id, district_id)
        assert new_quote.items_total_uzs == Decimal("240")
        order = await session.get(Order, order_id)
        quote = await session.get(Quote, order.quote_id)
        assert quote.items_total == Decimal("120")
        assert quote.payload["fx_snapshot"]["revision"] == 1
        assert Decimal(quote.payload["fx_snapshot"]["rate"]) == Decimal("10")
        assert order.grand_total_quoted == placed.order.grand_total_quoted


@pytest.mark.asyncio
async def test_waiting_quote_refreshes_preloaded_offer_and_tier_after_rate_commit(pg_sessions):
    _, product_id, admins, district_id, offer_id = await _priced_fixture(pg_sessions)
    started = asyncio.Event()
    async with pg_sessions() as reader, pg_sessions() as writer:
        # Session retains preloaded identity-mapped offer/tier values.
        old = await reader.scalar(select(ShopProduct).where(ShopProduct.id == offer_id))
        assert old.price_per_pack == Decimal("70")
        assert old.price_tiers[0].price_per_pack == Decimal("60")
        await reader.commit()
        await FxPricingService(writer).publish_rate(Decimal("20"), admins[0], 1)

        async def quote():
            started.set()
            return await _quote(reader, product_id, district_id)

        task = asyncio.create_task(quote())
        try:
            await started.wait()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.1)
            await writer.commit()
            variant = await asyncio.wait_for(task, 5)
            assert variant.items_total_uzs == Decimal("240")
            assert old.price_per_pack == Decimal("140")
            assert old.price_tiers[0].price_per_pack == Decimal("120")
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_two_admins_cannot_publish_the_same_expected_revision(pg_sessions):
    _, _, admins, _, _ = await _priced_fixture(pg_sessions)

    async def publish(rate, admin_id):
        async with pg_sessions() as session:
            try:
                await FxPricingService(session).publish_rate(Decimal(rate), admin_id, 1)
                await session.commit()
                return True
            except FxConflict:
                await session.rollback()
                return False

    assert sorted(await asyncio.gather(publish("20", admins[0]), publish("30", admins[1]))) == [
        False,
        True,
    ]
    async with pg_sessions() as session:
        snapshot = await FxPricingService(session).snapshot()
        offer = await session.scalar(select(ShopProduct))
        assert snapshot.revision == 2
        assert offer.price_per_pack == Decimal("7") * snapshot.rate
        assert offer.price_tiers[0].price_per_pack == Decimal("6") * snapshot.rate


async def _wait_for_database_lock(factory, pid, *, task=None):
    from sqlalchemy import text

    for _ in range(200):
        if task is not None and task.done():
            return
        async with factory() as observer:
            waiting = await observer.scalar(
                text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),
                {"pid": pid},
            )
        if waiting:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"backend {pid} never reached its expected lock")


@pytest.mark.asyncio
async def test_blocked_cart_read_does_not_block_global_rate_publication(pg_sessions):
    """One busy cart must not keep a global rate publication waiting."""
    from sqlalchemy import text

    from app.services.cart_service import CartService
    from app.web.storefront.routers.cart import get_cart

    user_id, product_id, admins, district_id, _ = await _priced_fixture(pg_sessions)
    async with pg_sessions() as checkout, pg_sessions() as reader, pg_sessions() as writer:
        await CartService(checkout).get(user_id)
        user = await reader.get(User, user_id)
        reader_pid = await reader.scalar(text("SELECT pg_backend_pid()"))
        reader_task = asyncio.create_task(get_cart(user=user, session=reader))
        writer_task = None
        try:
            # A reader queued behind a busy cart must not hold the global FX
            # lock before it can actually price that cart.
            await _wait_for_database_lock(pg_sessions, reader_pid)

            async def publish():
                await FxPricingService(writer).publish_rate(Decimal("20"), admins[0], 1)
                await writer.commit()

            writer_task = asyncio.create_task(publish())
            await asyncio.wait_for(asyncio.shield(writer_task), 2)
            variant = await asyncio.wait_for(_quote(checkout, product_id, district_id), 5)
            await checkout.commit()
            await asyncio.wait_for(asyncio.gather(reader_task, writer_task), 5)
            assert variant.items_total_uzs == Decimal("240")
        finally:
            pending = [task for task in (reader_task, writer_task) if task and not task.done()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
