"""Authenticated durable cart; guests keep a local draft until sign-in."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import localized_name
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.cart_policy import assess_lines
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.services.fx_pricing import FxPricingService
from app.services.guest_cart_claim_service import (
    preview_guest_cart,
    resolve_guest_cart_claim,
)
from app.web.storefront.cookies import clear_session_cookie
from app.web.storefront.deps import current_lang, require_api_user
from app.web.storefront.security import require_csrf
from app.web.storefront.session import GUEST_COOKIE

router = APIRouter(tags=["storefront"])


class CartItemIn(BaseModel):
    qty: str = Field(max_length=64)
    unit_code: str | None = None
    expected_revision: int = Field(ge=0)


class MergeLineIn(BaseModel):
    canonical_id: int = Field(gt=0)
    qty: str = Field(max_length=64)
    unit_code: str | None = None


class CartMergeIn(BaseModel):
    lines: list[MergeLineIn] = Field(max_length=60)
    merge_key: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=0)


class GuestCartClaimIn(BaseModel):
    drop_guest_ids: list[StrictInt] = Field(default_factory=list, max_length=60)
    remove_account_ids: list[StrictInt] = Field(default_factory=list, max_length=60)


async def _error(
    session: AsyncSession, user: User, exc: CartConflict | InvalidCartItem, lang: str
) -> JSONResponse:
    user_id = user.id
    await session.rollback()
    snapshot = await CartService(session).get(user_id)
    fx = await FxPricingService(session).snapshot(lock=True)
    lines = await assess_lines(session, snapshot.lines, rate=fx.rate, fx_revision=fx.revision)
    await session.commit()
    return JSONResponse(
        status_code=409 if isinstance(exc, CartConflict) else 422,
        content={
            **snapshot.payload(),
            "lines": lines,
            "fx_revision": fx.revision,
            "ok": False,
            "code": exc.message,
            "error": t("web_error_generic", lang=lang),
        },
    )


@router.get("/api/cart")
async def get_cart(
    user: User = Depends(require_api_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    snapshot = await CartService(session).get(user.id)
    fx = await FxPricingService(session).snapshot(lock=True)
    lines = await assess_lines(session, snapshot.lines, rate=fx.rate, fx_revision=fx.revision)
    await session.commit()
    return {
        **snapshot.payload(),
        "fx_revision": fx.revision,
        "lines": lines,
        "requires_confirmation": any(line["requires_confirmation"] for line in lines),
    }


@router.get("/api/cart/claim-guest")
async def guest_cart_claim_preview(
    request: Request,
    user: User = Depends(require_api_user),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> JSONResponse:
    """Show the guest cart bound to this browser's visitor cookie."""
    if user.tg_id is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "code": "telegram_login_required",
                "error": t("web_checkout_login_required", lang=lang),
            },
        )

    preview = await preview_guest_cart(session, user, request.cookies.get(GUEST_COOKIE))
    if preview is None:
        await session.commit()
        return JSONResponse({"ok": True, "status": "none", "source_lines": []})

    priced_lines = await assess_lines(session, list(preview.source_lines))
    product_ids = [line["canonical_id"] for line in priced_lines]
    products = {
        product.id: product
        for product in (
            await session.scalars(
                select(CanonicalProduct).where(CanonicalProduct.id.in_(product_ids))
            )
        ).all()
    }
    source_lines = []
    for line in priced_lines:
        product = products.get(line["canonical_id"])
        name = (
            localized_name(
                product.name_uz,
                product.name_ru,
                lang,
                name_uz_cyrl=product.name_uz_cyrl,
            )
            if product is not None
            else f"#{line['canonical_id']}"
        )
        source_lines.append(
            {
                "canonical_id": line["canonical_id"],
                "qty": line["qty"],
                "unit_code": line["unit_code"],
                "name": name,
                "requires_confirmation": line["requires_confirmation"],
            }
        )
    await session.commit()
    return JSONResponse({"ok": True, "status": "review_required", "source_lines": source_lines})


@router.put(
    "/api/cart/items/{product_id}", dependencies=[Depends(require_api_user), Depends(require_csrf)]
)
async def set_cart_item(
    product_id: int,
    body: CartItemIn,
    user: User = Depends(require_api_user),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Any:
    try:
        snapshot = await CartService(session).set_item(
            user.id,
            product_id,
            body.qty,
            expected_revision=body.expected_revision,
            unit_code=body.unit_code,
        )
    except (CartConflict, InvalidCartItem) as exc:
        return await _error(session, user, exc, lang)
    await session.commit()
    return snapshot.payload()


@router.delete(
    "/api/cart/items/{product_id}", dependencies=[Depends(require_api_user), Depends(require_csrf)]
)
async def delete_cart_item(
    product_id: int,
    expected_revision: int = Query(ge=0),
    user: User = Depends(require_api_user),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Any:
    try:
        snapshot = await CartService(session).remove_item(
            user.id, product_id, expected_revision=expected_revision
        )
    except CartConflict as exc:
        return await _error(session, user, exc, lang)
    await session.commit()
    return snapshot.payload()


@router.post("/api/cart/merge", dependencies=[Depends(require_api_user), Depends(require_csrf)])
async def merge_cart(
    body: CartMergeIn,
    user: User = Depends(require_api_user),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> Any:
    try:
        snapshot = await CartService(session).merge(
            user.id,
            [line.model_dump() for line in body.lines],
            merge_key=f"guest:{body.merge_key}",
            expected_revision=body.expected_revision,
        )
    except (CartConflict, InvalidCartItem) as exc:
        return await _error(session, user, exc, lang)
    await session.commit()
    return snapshot.payload()


@router.post(
    "/api/cart/claim-guest",
    dependencies=[Depends(require_api_user), Depends(require_csrf)],
)
async def retry_guest_cart_claim(
    request: Request,
    body: GuestCartClaimIn | None = None,
    user: User = Depends(require_api_user),
    session: AsyncSession = Depends(get_db_session),
    lang: str = Depends(current_lang),
) -> JSONResponse:
    """Retry this browser's guest-cart claim after the customer reviews a conflict."""
    if user.tg_id is None:
        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "code": "telegram_login_required",
                "error": t("web_checkout_login_required", lang=lang),
            },
        )

    try:
        result = await resolve_guest_cart_claim(
            session,
            user,
            request.cookies.get(GUEST_COOKIE),
            drop_guest_ids=body.drop_guest_ids if body is not None else (),
            remove_account_ids=body.remove_account_ids if body is not None else (),
        )
    except (CartConflict, InvalidCartItem) as exc:
        # Catalog state can change after the dry-run validation. Roll back any
        # explicit account-line removals and leave both carts available to retry.
        await session.rollback()
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "code": "guest_cart_review_required",
                "reason": exc.message,
                "error": t("guest_claim_still_conflicts", lang=lang),
            },
        )
    if result.needs_review:
        await session.commit()
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "code": "guest_cart_review_required",
                "reason": result.reason,
                "error": t("guest_claim_still_conflicts", lang=lang),
            },
        )

    if result.status == "invalid_selection":
        await session.commit()
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "code": result.reason,
                "error": t("guest_claim_selection_invalid", lang=lang),
            },
        )

    await session.commit()
    response = JSONResponse({"ok": True, "status": result.status})
    if result.claimed:
        clear_session_cookie(response, request, GUEST_COOKIE)
    return response
