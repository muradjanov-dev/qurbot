"""Turning a chosen quote variant into a real order.

One place decides what an order *is*: a basket, an immutable quote snapshot,
an order, and the per-shop parts the sourcing splits into -- plus the pebbles
the customer earned, granted inside the same transaction so a customer can
never see "order placed" without them.

Everything is sold from QurBot's own stock, so the per-shop parts always name
the one house shop; they are kept because the order schema and the optimizer
still speak in shop groups. The admins are the only people told about an
order -- there is no third party to notify.

Both doorways come through here -- the bot's confirm button and the website's
checkout -- so an order means the same thing whichever way it was placed, and a
change to what an order *is* cannot land on one and miss the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import get_admin_order_decision_keyboard
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.order import Basket, Order, OrderItem, OrderShopPart, Quote
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.domain.optimizer.models import QuoteVariant, ShopQuoteGroup
from app.domain.optimizer.serde import serialize_variant
from app.domain.rewards import pebbles_for_order

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PlacedOrder:
    """What `place_order` wrote, in the form the caller needs to report it."""

    order: Order
    pebbles: int
    parts: tuple[tuple[OrderShopPart, ShopQuoteGroup], ...]
    # Which doorway the order came through. Only the admin notification uses
    # it, and only to say so -- an operator chasing an order wants to know
    # where the customer is, and the two channels reach them differently.
    source: str = "bot"


def _format_qty(value: Decimal) -> str:
    return format(value.normalize(), "f")


async def place_order(
    session: AsyncSession,
    *,
    user: User,
    variant: QuoteVariant,
    contact_phone: str,
    delivery_address: str,
    delivery_lat: Decimal | None = None,
    delivery_lng: Decimal | None = None,
    comment: str | None = None,
    raw_text: str = "",
    source: str = "web",
) -> PlacedOrder:
    """Persist a basket, its quote snapshot, the order, and its shop parts.

    Flushes but does not commit: the caller owns the transaction boundary, so
    that an order and whatever else it triggers land together or not at all.
    """
    basket = Basket(user_id=user.id, raw_text=raw_text or "web basket", status="ordered")
    session.add(basket)
    await session.flush()

    strategy = variant.strategy_labels[0].value if variant.strategy_labels else "CHEAPEST_TOTAL"
    quote = Quote(
        basket_id=basket.id,
        strategy=strategy,
        items_total=variant.items_total_uzs,
        delivery_total=variant.delivery_total_uzs,
        grand_total=variant.grand_total_uzs,
        coverage_pct=Decimal(str(variant.coverage_pct)),
        shop_count=len(variant.shop_groups),
        eta_hours=variant.max_eta_hours,
        missing_line_ids=[item.line_no for item in variant.missing_lines],
        # The snapshot SPEC §4.3 asks for: prices move, and the order has to
        # keep pointing at what was actually quoted.
        payload=serialize_variant(variant),
    )
    session.add(quote)
    await session.flush()

    order = Order(
        quote_id=quote.id,
        user_id=user.id,
        status="new",
        contact_phone=contact_phone,
        delivery_address=delivery_address,
        # Only a complete pin is stored: half a coordinate is not a place.
        delivery_lat=delivery_lat if delivery_lng is not None else None,
        delivery_lng=delivery_lng if delivery_lat is not None else None,
        comment=comment,
        grand_total_quoted=variant.grand_total_uzs,
    )
    session.add(order)
    await session.flush()

    parts: list[tuple[OrderShopPart, ShopQuoteGroup]] = []
    for group in variant.shop_groups:
        part = OrderShopPart(
            order_id=order.id,
            shop_id=group.shop_id,
            subtotal=group.subtotal_uzs,
            delivery_fee=group.delivery_fee_uzs,
            status="new",
            shop_response="pending",
        )
        session.add(part)
        await session.flush()
        parts.append((part, group))

        for line in group.lines:
            session.add(
                OrderItem(
                    order_shop_part_id=part.id,
                    canonical_id=line.canonical_id,
                    shop_product_id=line.offer_id,
                    qty=line.billed_qty,
                    unit_code=line.pack_unit,
                    unit_price_quoted=line.unit_price_uzs,
                    line_total=line.line_cost_uzs,
                )
            )

    ops_repo = OpsRepository(session)
    pebbles = pebbles_for_order(order.grand_total_quoted, settings.pebble_rate_per_order)
    if pebbles > 0:
        await ops_repo.award_pebbles(
            user_id=user.id, amount=pebbles, source="order", order_id=order.id
        )

    await ops_repo.log_event(
        "order_created",
        user_id=user.id,
        props={
            "order_id": order.id,
            "source": source,
            "strategy": strategy,
            "shop_count": len(variant.shop_groups),
            "grand_total": str(variant.grand_total_uzs),
        },
    )
    await session.flush()

    return PlacedOrder(order=order, pebbles=pebbles, parts=tuple(parts), source=source)


async def notify_order(
    bot: Bot,
    session: AsyncSession,
    placed: PlacedOrder,
    *,
    user: User,
) -> None:
    """Tell the admins about a new order.

    Best-effort by design: this runs after the order is committed, so a failed
    send is logged and skipped rather than allowed to fail an order that
    already exists.
    """
    order = placed.order
    customer_name = user.full_name or str(user.tg_id)
    phone = order.contact_phone
    address = order.delivery_address

    admin_sections: list[str] = []
    items_total = Decimal("0")
    delivery_total = Decimal("0")
    for part, group in placed.parts:
        items_total += part.subtotal
        delivery_total += part.delivery_fee
        lines_str = "\n".join(
            f"   • {escape(line.product_name)} × {_format_qty(line.billed_qty)} "
            f"{escape(line.pack_unit)} — {line.line_cost_uzs:,.0f} so'm"
            for line in group.lines
        )
        admin_sections.append(
            f"{lines_str}\n"
            f"   <i>Jami: {part.subtotal:,.0f} + dostavka {part.delivery_fee:,.0f} so'm</i>"
        )

    comment_line = f"💬 Izoh: {escape(order.comment)}\n" if order.comment else ""
    channel = " (sayt)" if placed.source == "web" else ""
    admin_text = (
        f"📦 <b>Yangi buyurtma #{order.id}</b>{channel}\n\n"
        f"👤 Mijoz: {escape(customer_name)}\n"
        f"📞 Tel: {escape(phone)}\n"
        f"📍 Manzil: {escape(address)}\n"
        f"{comment_line}"
        f"\n" + "\n\n".join(admin_sections) + "\n\n"
        f"──────────────────────────\n"
        f"Mahsulotlar: {items_total:,.0f} so'm\n"
        f"Dostavka: {delivery_total:,.0f} so'm\n"
        f"<b>JAMI: {order.grand_total_quoted:,.0f} so'm</b>"
    )
    lat, lng = order.delivery_lat, order.delivery_lng
    for admin_id in settings.admin_tg_ids:
        try:
            sent = await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=get_admin_order_decision_keyboard(order.id),
            )
        except TelegramAPIError as exc:
            logger.warning("admin_order_notify_failed", admin_id=admin_id, error=str(exc))
            continue
        if lat is None or lng is None:
            continue
        # The text alone is not enough to deliver on: a typed Tashkent address
        # often does not resolve to a findable place. The pin goes as a native
        # location, threaded under the order so the two are never confused
        # when several orders arrive together.
        try:
            await bot.send_location(
                admin_id,
                latitude=float(lat),
                longitude=float(lng),
                reply_to_message_id=getattr(sent, "message_id", None),
            )
        except TelegramAPIError as exc:
            logger.warning("admin_order_location_failed", admin_id=admin_id, error=str(exc))
