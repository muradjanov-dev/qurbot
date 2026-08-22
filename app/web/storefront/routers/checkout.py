"""Checkout: who is receiving the order, where, and confirming the price."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_uzs
from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.order import Order
from app.db.models.user import User
from app.db.repositories.address_repo import AddressRepository
from app.db.session import get_db_session
from app.domain.normalize.phone import normalize_uz_phone
from app.services.address_service import AddressService, ResolvedLocation
from app.services.order_service import notify_order, place_order
from app.web.storefront.deps import current_lang, current_user, render, require_api_user
from app.web.storefront.quoting import optimize, pick_variant, validate_lines, variant_payload
from app.web.storefront.schemas import OrderIn
from app.web.storefront.throttle import SlidingWindow, client_key

logger = get_logger(__name__)

router = APIRouter(tags=["storefront"])

_GEOCODE_THROTTLE = SlidingWindow(limit=settings.throttle_limit_per_minute)


@router.get("/checkout")
async def checkout_page(
    request: Request,
    strategy: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    if user is None:
        return RedirectResponse(
            "/login?next=/checkout&msg=web_checkout_login_required", status_code=303
        )

    addresses = await AddressService(session).list_for(user)
    last_phone = await _last_used_phone(session, user)
    return render(
        request,
        "checkout.html",
        user=user,
        lang=lang,
        addresses=addresses,
        last_phone=last_phone,
        strategy=strategy or "",
    )


async def _last_used_phone(session: AsyncSession, user: User) -> str:
    """The number this customer gave last time, so they need not retype it.

    Kept off the `users` table on purpose: the contact number belongs to an
    order (a site foreman may differ from the account holder), which is exactly
    how the bot treats it too.
    """
    stmt = (
        select(Order.contact_phone)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    return str((await session.execute(stmt)).scalars().first() or "")


@router.get("/api/geocode")
async def api_geocode(
    request: Request,
    lat: float = Query(...),
    lng: float = Query(...),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> dict[str, Any]:
    """Name the pin the browser dropped, so the customer can confirm or fix it."""
    if not _GEOCODE_THROTTLE.allow(client_key(request, user)):
        return {"ok": False, "error": t("web_error_generic", lang=lang)}

    resolved = await AddressService(session).resolve(lat, lng, lang=lang)
    return {
        "ok": True,
        "address": resolved.address_text or "",
        "district_id": resolved.district_id,
        "outside_service_area": resolved.outside_service_area,
        "notice": (
            t("address_outside_service_area", lang=lang) if resolved.outside_service_area else None
        ),
    }


@router.post("/api/order")
async def api_create_order(
    body: OrderIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_api_user),
    lang: str = Depends(current_lang),
) -> dict[str, Any]:
    """Create the order for the selected variant.

    The quote is recomputed here rather than taken from the browser: prices
    move between looking and buying, and an order must reference a price we can
    actually honour. If the total moved, the customer is shown the new one and
    asked again -- never charged the difference silently.
    """
    phone = normalize_uz_phone(body.phone)
    if phone is None:
        return {"ok": False, "error": t("web_checkout_phone_required", lang=lang)}

    address = await _resolve_address(session, user, body, lang=lang)
    if address is None:
        return {"ok": False, "error": t("web_checkout_address_required", lang=lang)}
    address_text, district_id = address

    basket = await validate_lines(session, [line.model_dump() for line in body.lines])
    if not basket.items:
        return {"ok": False, "error": t("web_basket_nothing_confirmed", lang=lang)}

    variants = await optimize(session, basket.items, district_id=district_id)
    variant = pick_variant(variants, body.strategy)
    if variant is None:
        return {"ok": False, "error": t("web_quote_empty", lang=lang)}

    if body.expected_total is not None:
        try:
            expected = Decimal(body.expected_total)
        except (ArithmeticError, ValueError):
            expected = None
        if expected is not None and expected != variant.grand_total_uzs:
            currency = t("web_currency", lang=lang)
            return {
                "ok": False,
                "price_changed": True,
                "variant": variant_payload(variant, lang),
                "error": t(
                    "web_checkout_price_changed",
                    lang=lang,
                    total=f"{format_uzs(variant.grand_total_uzs)} {currency}",
                ),
            }

    comment = (body.comment or "").strip() or None
    placed = await place_order(
        session,
        user=user,
        variant=variant,
        contact_phone=phone,
        delivery_address=address_text,
        comment=comment,
        raw_text="\n".join(
            f"{item.needed_qty} {item.unit_code} {item.name_uz}" for item in basket.items
        ),
    )
    # Committed before anyone is told about it: a notification for an order
    # that failed to save is worse than a saved order nobody was told about.
    await session.commit()

    bot = getattr(request.app.state, "bot", None)
    if bot is not None:
        await notify_order(bot, session, placed, user=user)

    return {
        "ok": True,
        "order_id": placed.order.id,
        "pebbles": placed.pebbles,
        "redirect": f"/orders/{placed.order.id}?msg=web_saved",
    }


async def _resolve_address(
    session: AsyncSession,
    user: User,
    body: OrderIn,
    *,
    lang: str,
) -> tuple[str, int | None] | None:
    """Work out where this order goes, saving a new place for next time.

    A saved address is re-read from the database rather than trusted from the
    request, and checked to belong to this customer -- the id came from a client.
    """
    repo = AddressRepository(session)

    if body.address_id is not None:
        stored = await repo.get(body.address_id)
        if stored is None or stored.user_id != user.id:
            return None
        return stored.address_text, stored.district_id

    typed = (body.address_text or "").strip()
    if not typed:
        return None

    if body.lat is None or body.lng is None:
        # Typed with no pin: usable for delivery, but there is nothing durable
        # to anchor a saved place on, so it is used for this order only.
        return typed, user.district_id

    service = AddressService(session)
    resolved = await service.resolve(body.lat, body.lng, lang=lang)
    saved = await service.save(
        user,
        ResolvedLocation(
            lat=resolved.lat,
            lng=resolved.lng,
            address_text=typed,
            district_id=resolved.district_id,
        ),
        typed,
        make_default=not await repo.get_default(user.id),
    )
    return saved.address_text, saved.district_id
