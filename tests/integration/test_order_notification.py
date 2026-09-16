"""A new order reaches the admins, and nobody else.

QurBot sells from its own stock; there is no partner shop to tell. The admins
get the whole picture -- customer, phone, address, goods -- because they are the
ones confirming and delivering the order.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.shop import District, Shop
from app.db.models.user import User
from app.domain.optimizer.models import LineAssignment, ShopQuoteGroup
from app.services.order_service import PlacedOrder, notify_order

CUSTOMER_NAME = "Sunnatilloh Aka"
CUSTOMER_PHONE = "+998901234567"
CUSTOMER_ADDRESS = "Chilonzor 9-kvartal, 42-uy"

# A leftover owner id on the shop row must not turn into a recipient.
LEGACY_OWNER_TG_ID = 5550001


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.markups: list[object | None] = []
        self.locations: list[tuple[int, float, float, object]] = []
        self._next_id = 100

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> SimpleNamespace:
        self.sent.append((chat_id, text))
        self.markups.append(kwargs.get("reply_markup"))
        self._next_id += 1
        return SimpleNamespace(message_id=self._next_id)

    async def send_location(
        self, chat_id: int, *, latitude: float, longitude: float, **kwargs: object
    ) -> None:
        self.locations.append((chat_id, latitude, longitude, kwargs.get("reply_to_message_id")))


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


@pytest.mark.asyncio
async def test_only_the_admins_are_told(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session)
    bot = FakeBot()

    await notify_order(bot, test_session, placed, user=user)  # type: ignore[arg-type]

    recipients = {chat_id for chat_id, _ in bot.sent}
    assert recipients == set(settings.admin_tg_ids)
    assert LEGACY_OWNER_TG_ID not in recipients


@pytest.mark.asyncio
async def test_the_admins_get_the_whole_picture(test_session: AsyncSession) -> None:
    """Someone has to confirm and deliver the order, and that someone is us."""
    placed, user = await _placed_order(test_session)
    bot = FakeBot()

    await notify_order(bot, test_session, placed, user=user)  # type: ignore[arg-type]

    joined = "\n".join(text for _, text in bot.sent)
    assert CUSTOMER_PHONE in joined
    assert CUSTOMER_ADDRESS in joined
    assert "Fanera 12 mm 1525x1525" in joined

    admin_markups = [
        markup
        for (chat_id, _text), markup in zip(bot.sent, bot.markups, strict=True)
        if chat_id in settings.admin_tg_ids
    ]
    assert admin_markups
    callbacks = [button.callback_data for row in admin_markups[0].inline_keyboard for button in row]
    assert callbacks == [
        f"admin_order:confirm:{placed.order.id}",
        f"admin_order:cancel:{placed.order.id}",
    ]


@pytest.mark.asyncio
async def test_each_admin_gets_the_pin_as_a_telegram_location(test_session: AsyncSession) -> None:
    """Words alone are not deliverable; the courier opens the pin."""
    placed, user = await _placed_order(test_session)
    bot = FakeBot()

    await notify_order(bot, test_session, placed, user=user)  # type: ignore[arg-type]

    assert {chat_id for chat_id, *_ in bot.locations} == set(settings.admin_tg_ids)
    for _, lat, lng, reply_to in bot.locations:
        assert (lat, lng) == (float(PIN_LAT), float(PIN_LNG))
        # Threaded under that admin's order message, so it cannot be mistaken
        # for another order's location.
        assert reply_to is not None


@pytest.mark.asyncio
async def test_a_typed_address_sends_no_location(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session, with_pin=False)
    bot = FakeBot()

    await notify_order(bot, test_session, placed, user=user)  # type: ignore[arg-type]

    assert bot.sent, "the order text still goes out"
    assert bot.locations == []
