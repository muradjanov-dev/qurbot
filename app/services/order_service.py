"""Turning a chosen quote variant into a real order.

One place decides what an order *is*: a basket, an immutable quote snapshot,
an order, and the per-shop parts the sourcing splits into -- plus the pebbles
the customer earned, granted inside the same transaction so a customer can
never see "order placed" without them.

Everything is sold from QurBot's own stock, so the per-shop parts always name
the one house shop; they are kept because the order schema and the optimizer
still speak in shop groups. Admins receive the new-order details and customers
receive status updates; there is no third party to notify.

Both doorways come through here -- the bot's confirm button and the website's
checkout -- so an order means the same thing whichever way it was placed, and a
change to what an order *is* cannot land on one and miss the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.cart import CheckoutAttempt
from app.db.models.order import Basket, Order, OrderItem, OrderShopPart, Quote
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.domain.optimizer.models import QuoteVariant, ShopQuoteGroup
from app.domain.optimizer.serde import serialize_variant
from app.domain.rewards import pebbles_for_order
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.services.fx_pricing import FxPricingService
from app.services.order_workflow import OrderWorkflowService


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
    replayed: bool = False


def checkout_fingerprint(payload: dict[str, object]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def checkout_replay(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
    fingerprint: str,
) -> PlacedOrder | None:
    if not idempotency_key or len(idempotency_key) > 160:
        raise InvalidCartItem("invalid_idempotency_key")
    await CartService(session).lock(user_id)
    receipt = await session.get(CheckoutAttempt, (user_id, idempotency_key))
    if receipt is None:
        return None
    if receipt.fingerprint != fingerprint:
        raise InvalidCartItem("idempotency_conflict")
    order = await session.scalar(
        select(Order).where(Order.id == receipt.order_id, Order.user_id == user_id)
    )
    assert order is not None
    return PlacedOrder(order=order, pebbles=0, parts=(), replayed=True)


async def place_order(
    session: AsyncSession,
    *,
    user: User,
    variant: QuoteVariant,
    contact_phone: str,
    delivery_address: str,
    contact_name: str | None = None,
    delivery_lat: Decimal | None = None,
    delivery_lng: Decimal | None = None,
    comment: str | None = None,
    raw_text: str = "",
    source: str = "web",
    idempotency_key: str | None = None,
    fingerprint: str | None = None,
    cart_revision: int | None = None,
) -> PlacedOrder:
    """Persist a basket, its quote snapshot, the order, and its shop parts.

    Flushes but does not commit: the caller owns the transaction boundary, so
    that an order and whatever else it triggers land together or not at all.
    """
    if idempotency_key is not None:
        if fingerprint is None:
            raise InvalidCartItem("missing_fingerprint")
        replay = await checkout_replay(
            session, user_id=user.id, idempotency_key=idempotency_key, fingerprint=fingerprint
        )
        if replay is not None:
            return replay
    # A legacy receipt remains replayable; only a newly created order needs Telegram.
    if user.tg_id is None or user.is_blocked:
        raise InvalidCartItem("telegram_login_required")
    if not variant.is_orderable or variant.missing_lines:
        raise InvalidCartItem("quote_not_orderable")
    cart_service: CartService | None = None
    snapshot = None
    if cart_revision is not None:
        # Keep lock order consistent with checkout quote paths: cart row first,
        # then the shared FX row. A queued FX publisher must not sit between
        # these locks and create a cycle with another cart reader.
        cart_service = CartService(session)
        snapshot = await cart_service.get(user.id)
        if snapshot.revision != cart_revision:
            raise CartConflict(snapshot.revision)

    # QuoteService already holds this shared lock for the normal quote-to-order
    # request path; the acquisition here also covers precomputed variants.
    fx_snapshot = await FxPricingService(session).snapshot(lock=True)

    if cart_revision is not None:
        assert cart_service is not None and snapshot is not None
        # Clear in the SAME transaction as order/reward/receipt creation.
        from app.services.cart_policy import assess_lines

        if any(
            line["requires_confirmation"] for line in await assess_lines(session, snapshot.lines)
        ):
            raise InvalidCartItem("operator_confirmation_required")
        quoted_ids = {line.canonical_id for group in variant.shop_groups for line in group.lines}
        if quoted_ids != {line["canonical_id"] for line in snapshot.lines}:
            raise InvalidCartItem("incomplete_quote")
        for product_id in {
            line.canonical_id for group in variant.shop_groups for line in group.lines
        }:
            snapshot = await cart_service.remove_item(
                user.id, product_id, expected_revision=snapshot.revision
            )
    basket = Basket(user_id=user.id, raw_text=raw_text or "web basket", status="ordered")
    session.add(basket)
    await session.flush()

    strategy = variant.strategy_labels[0].value if variant.strategy_labels else "CHEAPEST_TOTAL"
    quote_payload = serialize_variant(variant)
    quote_payload["fx_snapshot"] = {
        "rate": str(fx_snapshot.rate) if fx_snapshot.rate is not None else None,
        "revision": fx_snapshot.revision,
        "updated_at": fx_snapshot.updated_at.isoformat() if fx_snapshot.updated_at else None,
        "updated_by": fx_snapshot.updated_by,
    }
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
        payload=quote_payload,
    )
    session.add(quote)
    await session.flush()

    order = Order(
        is_test=user.is_test or user.tg_id in settings.test_tg_ids,
        quote_id=quote.id,
        user_id=user.id,
        status="new",
        contact_phone=contact_phone,
        contact_name=contact_name or user.full_name,
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
    pebbles = (
        0
        if order.is_test
        else pebbles_for_order(order.grand_total_quoted, settings.pebble_rate_per_order)
    )
    if pebbles > 0:
        await ops_repo.award_pebbles(
            user_id=user.id, amount=pebbles, source="order", order_id=order.id
        )

    await ops_repo.log_event(
        "test_order_created" if order.is_test else "order_created",
        user_id=user.id,
        props={
            "order_id": order.id,
            "source": source,
            "strategy": strategy,
            "shop_count": len(variant.shop_groups),
            "grand_total": str(variant.grand_total_uzs),
        },
    )
    await ops_repo.log_event(
        "test_checkout_confirmed" if order.is_test else "checkout_confirmed",
        user_id=user.id,
        props={"order_id": order.id, "source": source, "cart_revision": cart_revision},
    )
    if idempotency_key is not None:
        session.add(
            CheckoutAttempt(
                user_id=user.id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                order_id=order.id,
            )
        )
    await session.flush()

    await OrderWorkflowService(session).create_event(order, user, source=source)
    return PlacedOrder(order=order, pebbles=pebbles, parts=tuple(parts), source=source)


async def notify_order(
    bot: Bot,
    session: AsyncSession,
    placed: PlacedOrder,
    *,
    user: User,
) -> None:
    """Compatibility hook: creation already persisted the durable notification queue.

    Callers can keep invoking this after commit. It must not send directly or
    add a second event: the worker delivers the rows created by ``place_order``.
    """
    return None
