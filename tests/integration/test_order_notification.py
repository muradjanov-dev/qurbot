"""A new order reaches the admins, and nobody else.

QurBot sells from its own stock; there is no partner shop to tell. The admins
get the whole picture -- customer, phone, address, goods -- because they are the
ones confirming and delivering the order.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.order import Basket, Order, OrderItem, OrderShopPart, Quote
from app.db.models.order_workflow import OrderNotification
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User
from app.domain.optimizer.models import LineAssignment, ShopQuoteGroup
from app.services.order_service import PlacedOrder, notify_order
from app.services.order_workflow import OrderWorkflowService

CUSTOMER_NAME = "Sunnatilloh Aka"
CUSTOMER_PHONE = "+998901234567"
CUSTOMER_ADDRESS = "Chilonzor 9-kvartal, 42-uy"

# A leftover owner id on the shop row must not turn into a recipient.
LEGACY_OWNER_TG_ID = 5550001


PIN_LAT = Decimal("41.2856800")
PIN_LNG = Decimal("69.2034600")


async def _placed_order(
    session: AsyncSession, *, with_pin: bool = True
) -> tuple[PlacedOrder, User]:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()

    shop = Shop(
        name=settings.house_shop_name,
        phone=settings.house_shop_phone,
        district_id=district.id,
        address="Toshkent",
        owner_tg_id=LEGACY_OWNER_TG_ID,
        is_active=True,
    )
    user = User(tg_id=424242, lang="uz_latn", full_name=CUSTOMER_NAME)
    session.add_all([shop, user])
    await session.flush()

    basket = Basket(user_id=user.id, raw_text="10 dona fanera 12mm", status="quoted")
    session.add(basket)
    await session.flush()
    quote = Quote(
        basket_id=basket.id,
        strategy="cheapest",
        items_total=Decimal("1470000"),
        delivery_total=Decimal("40000"),
        grand_total=Decimal("1510000"),
        coverage_pct=Decimal("100"),
        shop_count=1,
    )
    session.add(quote)
    await session.flush()

    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        status="new",
        contact_phone=CUSTOMER_PHONE,
        delivery_address=CUSTOMER_ADDRESS,
        delivery_lat=PIN_LAT if with_pin else None,
        delivery_lng=PIN_LNG if with_pin else None,
        grand_total_quoted=Decimal("1510000"),
    )
    session.add(order)
    await session.flush()

    part = OrderShopPart(
        order_id=order.id,
        shop_id=shop.id,
        subtotal=Decimal("1470000"),
        delivery_fee=Decimal("40000"),
        status="pending",
    )
    session.add(part)
    await session.flush()

    category = Category(slug="plywood", name_uz="Fanera", name_ru="Фанера")
    session.add_all([category, Unit(code="dona", name_uz="Dona", name_ru="Шт", dimension="count")])
    await session.flush()
    product = CanonicalProduct(
        slug="plywood-12",
        name_uz="Fanera 12 mm 1525x1525",
        name_uz_cyrl="Фанера 12 мм",
        name_ru="Фанера 12 мм",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="fanera",
    )
    session.add(product)
    await session.flush()
    offer = ShopProduct(
        shop_id=shop.id,
        canonical_id=product.id,
        raw_name=product.name_uz,
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("147000"),
        price_per_base_unit=Decimal("147000"),
        stock_status="in_stock",
    )
    session.add(offer)
    await session.flush()
    session.add(
        OrderItem(
            order_shop_part_id=part.id,
            canonical_id=product.id,
            shop_product_id=offer.id,
            qty=Decimal("10"),
            unit_code="dona",
            unit_price_quoted=Decimal("147000"),
            line_total=Decimal("1470000"),
        )
    )
    await session.flush()
    group = ShopQuoteGroup(
        shop_id=shop.id,
        shop_name=shop.name,
        lines=(
            LineAssignment(
                line_no=1,
                canonical_id=1,
                product_name="Fanera 12 mm 1525x1525",
                shop_id=shop.id,
                shop_name=shop.name,
                offer_id=1,
                needed_qty=Decimal("10"),
                needed_unit="dona",
                pack_size=Decimal("1"),
                pack_unit="dona",
                packs_needed=10,
                billed_qty=Decimal("10"),
                overage_qty=Decimal("0"),
                unit_price_uzs=Decimal("147000"),
                line_cost_uzs=Decimal("1470000"),
            ),
        ),
        district_name="Chilonzor",
        distance_km=3.2,
        subtotal_uzs=Decimal("1470000"),
        delivery_fee_uzs=Decimal("40000"),
        is_free_delivery=False,
        eta_hours=24,
        trust_score=0.5,
    )
    return PlacedOrder(order=order, pebbles=0, parts=((part, group),)), user


async def _queue(session: AsyncSession, placed: PlacedOrder, user: User) -> list[OrderNotification]:
    await OrderWorkflowService(session).create_event(placed.order, user, source="bot")
    await session.commit()
    return list(
        (await session.scalars(select(OrderNotification).order_by(OrderNotification.id))).all()
    )


@pytest.mark.asyncio
async def test_only_the_admins_are_told(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session)
    rows = await _queue(test_session, placed, user)
    assert {row.recipient_tg_id for row in rows} == set(settings.admin_tg_ids)
    assert LEGACY_OWNER_TG_ID not in {row.recipient_tg_id for row in rows}
    bot = AsyncMock()
    await notify_order(bot, test_session, placed, user=user)
    # Worker owns delivery, never the checkout request.
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_the_admins_get_the_whole_picture(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session)
    rows = await _queue(test_session, placed, user)
    messages = [row for row in rows if row.kind == "admin_order_created"]
    assert messages
    joined = "\n".join(row.text for row in messages)
    assert CUSTOMER_PHONE in joined and CUSTOMER_ADDRESS in joined
    assert "Фанера 12 мм" in joined or "Fanera 12 mm 1525x1525" in joined
    assert "1 510 000" in joined
    keyboard = messages[0].payload["reply_markup"]["inline_keyboard"]
    callbacks = [
        button["callback_data"] for row in keyboard for button in row if "callback_data" in button
    ]
    assert callbacks == [f"admin_order:confirm:{placed.order.id}"]
    cancel_button = next(button for row in keyboard for button in row if "url" in button)
    assert cancel_button["text"] == "❌ Buyurtmani bekor qilish"
    assert cancel_button["url"].endswith(f"/manage/orders/{placed.order.id}")


@pytest.mark.asyncio
async def test_each_admin_gets_a_durable_threaded_pin(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session)
    rows = await _queue(test_session, placed, user)
    by_id = {row.id: row for row in rows}
    locations = [row for row in rows if row.kind == "admin_order_location"]
    assert {row.recipient_tg_id for row in locations} == set(settings.admin_tg_ids)
    for row in locations:
        assert row.payload["latitude"] == float(PIN_LAT)
        assert row.payload["longitude"] == float(PIN_LNG)
        parent = by_id[row.payload["reply_to_notification_id"]]
        assert (
            parent.kind == "admin_order_created" and parent.recipient_tg_id == row.recipient_tg_id
        )
        assert parent.id < row.id


@pytest.mark.asyncio
async def test_a_typed_address_queues_no_location(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session, with_pin=False)
    rows = await _queue(test_session, placed, user)
    assert rows and {row.kind for row in rows} == {"admin_order_created"}
