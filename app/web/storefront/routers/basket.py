"""The basket page and the JSON endpoints behind it.

The basket lives in the browser: it is the customer's own scratch list, and it
should survive a reload without forcing an account first. Everything that costs
money is decided here, server-side -- the client sends product ids and
quantities, never prices.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import t
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.session import get_db_session
from app.domain.parsing.parser import is_qty_orderable
from app.services.pdf_service import generate_quote_pdf
from app.web.storefront.deps import current_lang, current_user, render
from app.web.storefront.quoting import (
    line_for_product,
    optimize,
    parse_basket_text,
    pick_variant,
    validate_lines,
    variant_payload,
)
from app.web.storefront.schemas import ParseIn, ProductLineIn, QuoteIn
from app.web.storefront.throttle import SlidingWindow, client_key

router = APIRouter(tags=["storefront"])

# Parsing and optimizing are the two endpoints that do real work per call, so
# they share the bot's per-minute quote budget (SPEC §9).
_QUOTE_THROTTLE = SlidingWindow(limit=settings.throttle_quote_limit_per_minute)
_PARSE_THROTTLE = SlidingWindow(limit=settings.throttle_limit_per_minute)


def _guard(window: SlidingWindow, request: Request, user: User | None) -> None:
    if not window.allow(client_key(request, user)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_requests",
        )


@router.get("/basket", response_class=HTMLResponse)
async def basket_page(
    request: Request,
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    return render(request, "basket.html", user=user, lang=lang)


@router.post("/api/basket/parse")
async def api_parse(
    body: ParseIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> dict[str, Any]:
    """Parse a free-text list into basket lines, matched against the catalogue."""
    text = body.text.strip()
    if not text:
        return {"ok": False, "error": t("web_basket_parse_failed", lang=lang)}
    _guard(_PARSE_THROTTLE, request, user)

    lines = await parse_basket_text(
        session,
        text,
        start_no=max(0, body.start_no),
        user_id=user.id if user else None,
        lang=lang,
    )
    if not lines:
        return {"ok": False, "error": t("web_basket_parse_failed", lang=lang)}
    return {"ok": True, "lines": lines}


@router.post("/api/basket/product")
async def api_add_product(
    body: ProductLineIn,
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> dict[str, Any]:
    """Add a catalogue product to the basket at a chosen quantity."""
    try:
        qty = Decimal(body.qty.strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        return {"ok": False, "error": t("qty_out_of_range", lang=lang)}
    if not is_qty_orderable(qty, max_qty=Decimal(settings.basket_max_qty)):
        return {"ok": False, "error": t("qty_out_of_range", lang=lang)}

    product = await CatalogRepository(session).get(body.canonical_id)
    if product is None or not product.is_active:
        return {"ok": False, "error": t("web_not_found", lang=lang)}

    return {
        "ok": True,
        "line": line_for_product(product, qty, max(1, body.line_no)),
    }


@router.post("/api/quote")
async def api_quote(
    body: QuoteIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> dict[str, Any]:
    """Price the basket, returning one card per distinct sourcing plan."""
    _guard(_QUOTE_THROTTLE, request, user)

    basket = await validate_lines(session, [line.model_dump() for line in body.lines])
    if not basket.items:
        return {"ok": False, "error": t("web_basket_nothing_confirmed", lang=lang)}

    district_id = user.district_id if user else None
    variants = await optimize(session, basket.items, district_id=district_id)
    if not variants:
        return {"ok": False, "error": t("web_quote_empty", lang=lang)}

    return {
        "ok": True,
        "variants": [
            variant_payload(variant, lang, delivery_known=district_id is not None)
            for variant in variants
        ],
    }


@router.post("/api/quote/pdf")
async def api_quote_pdf(
    body: QuoteIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    """The selected variant as a downloadable offer sheet."""
    _guard(_QUOTE_THROTTLE, request, user)

    basket = await validate_lines(session, [line.model_dump() for line in body.lines])
    variants = await optimize(session, basket.items, district_id=user.district_id if user else None)
    variant = pick_variant(variants, body.strategy)
    if variant is None:
        raise HTTPException(status_code=404, detail="no_quote")

    # reportlab draws synchronously, so it goes to a thread rather than
    # blocking the event loop (CLAUDE.md: no blocking calls in handlers).
    pdf_bytes = await asyncio.to_thread(generate_quote_pdf, variant)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="qurbot-taklif.pdf"'},
    )
