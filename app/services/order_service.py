"""Turning a chosen quote variant into a real order.

One place decides what an order *is*: a basket, an immutable quote snapshot,
an order, and the per-shop parts the sourcing splits into -- plus the pebbles
the customer earned, granted inside the same transaction so a customer can
never see "order placed" without them.

The customer-facing half of an order is deliberately white-labelled (they buy
from QurBot, not from a list of vendors), so shop identity only ever appears in
the two places that need it: `order_shop_parts`, and the notifications this
module sends to the shops themselves and to the admin group.

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

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.order import Basket, Order, OrderItem, OrderShopPart, Quote
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
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
    """Tell each shop its part of the order, and the admins the whole thing.

    Best-effort by design: this runs after the order is committed, so a shop
    with no `owner_tg_id` on file or a failed send is logged and skipped rather
    than allowed to fail an order that already exists.
    """
    order = placed.order
    shop_repo = ShopRepository(session)
    customer_name = user.full_name or str(user.tg_id)
    phone = order.contact_phone
    address = order.delivery_address

    for part, group in placed.parts:
        shop = await shop_repo.get(part.shop_id)
        if not shop or not shop.owner_tg_id:
            continue
        lines_str = "\n".join(
            f"• {escape(line.product_name)} × {_format_qty(line.billed_qty)} "
            f"{escape(line.pack_unit)}"
            for line in group.lines
        )
        # A shop is told what to prepare and nothing about who it is for.
        # QurBot collects from the shop and delivers; the customer and the shop
        # never deal with each other. Sending the name, phone and address here
        # handed a shop everything it needed to go around us -- and handed a
        # customer's personal details to a third party that has no use for
        # them. The admins get the full picture; they are the ones arranging
        # the pickup.
        text = (
            f"🆕 <b>Yangi buyurtma #{order.id}</b>\n\n"
            f"{lines_str}\n\n"
            f"Mollar summasi: <b>{part.subtotal:,.0f} so'm</b>\n\n"
            f"📦 Iltimos, tayyorlab qo'ying — <b>kuryerimiz olib ketadi</b>.\n"
            f"Mijoz bilan bog'lanish shart emas, hammasi QurBot orqali."
        )
        try:
            await bot.send_message(shop.owner_tg_id, text)
        except TelegramAPIError as exc:
            logger.warning("shop_order_notify_failed", shop_id=shop.id, error=str(exc))

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
            f"🏪 <b>{escape(group.shop_name)}</b>\n"
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
    for admin_id in settings.admin_tg_ids:
        try:
            await bot.send_message(admin_id, admin_text)
        except TelegramAPIError as exc:
            logger.warning("admin_order_notify_failed", admin_id=admin_id, error=str(exc))
