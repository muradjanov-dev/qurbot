"""A shop is told what to prepare, and nothing about who it is for.

QurBot buys from the shop and delivers to the customer; the two never deal with
each other. The shop notification used to carry the customer's name, phone and
delivery address -- everything a shop needs to go around the platform on the
next order, and personal data handed to a third party with no use for it.

The admins still get the whole picture: they are the ones arranging the pickup.
"""

from __future__ import annotations

from decimal import Decimal

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

OWNER_TG_ID = 5550001


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


async def _placed_order(session: AsyncSession) -> tuple[PlacedOrder, User]:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()

    shop = Shop(
        name="Ark buloq",
        phone="+998901112233",
        district_id=district.id,
        address="Chilonzor 9",
        owner_tg_id=OWNER_TG_ID,
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
async def test_the_shop_never_learns_who_the_customer_is(test_session: AsyncSession) -> None:
    placed, user = await _placed_order(test_session)
    bot = FakeBot()

    await notify_order(bot, test_session, placed, user=user)  # type: ignore[arg-type]

    shop_messages = [text for chat_id, text in bot.sent if chat_id == OWNER_TG_ID]
    assert shop_messages, "the shop still has to be told to prepare the goods"
    message = shop_messages[0]

    assert CUSTOMER_PHONE not in message
    assert CUSTOMER_ADDRESS not in message
    assert CUSTOMER_NAME not in message

    # What it must contain: the goods, and who is collecting them.
    assert "Fanera 12 mm 1525x1525" in message
    assert "kuryerimiz" in message.lower()


@pytest.mark.asyncio
async def test_the_admins_still_get_the_whole_picture(test_session: AsyncSession) -> None:
    """Someone has to arrange the pickup, and that someone is us."""
    placed, user = await _placed_order(test_session)
    bot = FakeBot()

    await notify_order(bot, test_session, placed, user=user)  # type: ignore[arg-type]

    admin_messages = [text for chat_id, text in bot.sent if chat_id in settings.admin_tg_ids]
    assert admin_messages
    joined = "\n".join(admin_messages)
    assert CUSTOMER_PHONE in joined
    assert CUSTOMER_ADDRESS in joined
    assert "Ark buloq" in joined
