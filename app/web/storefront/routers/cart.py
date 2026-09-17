"""Authenticated durable cart; guests keep a local draft until sign-in."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.web.storefront.deps import current_lang, require_api_user
from app.web.storefront.security import require_csrf

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


async def _error(
    session: AsyncSession, user: User, exc: CartConflict | InvalidCartItem, lang: str
) -> JSONResponse:
    user_id = user.id
    await session.rollback()
    snapshot = await CartService(session).get(user_id)
    await session.commit()
    return JSONResponse(
        status_code=409 if isinstance(exc, CartConflict) else 422,
        content={
            **snapshot.payload(),
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
    await session.commit()
    return snapshot.payload()


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
