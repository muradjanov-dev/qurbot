"""The customer's own order history."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.db.repositories.order_repo import OrderRepository
from app.db.session import get_db_session
from app.web.storefront.deps import current_lang, current_user, render

router = APIRouter(tags=["storefront"])


@router.get("/orders")
async def orders_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    if user is None:
        return RedirectResponse("/login?next=/orders", status_code=303)

    orders = await OrderRepository(session).get_customer_orders(
        user.id, limit=settings.web_orders_page_size
    )
    return render(request, "orders.html", user=user, lang=lang, orders=orders)


@router.get("/orders/{order_id}")
async def order_detail(
    order_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    if user is None:
        return RedirectResponse(f"/login?next=/orders/{order_id}", status_code=303)

    order = await OrderRepository(session).get(order_id)
    if order is None or order.user_id != user.id:
        # Someone else's order is "not found", not "forbidden": confirming an
        # id exists is itself something a stranger should not learn.
        raise HTTPException(status_code=404, detail="order_not_found")

    return render(
        request,
        "order_detail.html",
        user=user,
        lang=lang,
        order=order,
        items=_flatten_items(order, lang),
        items_total=order.quote.items_total if order.quote else Decimal("0"),
        delivery_total=order.quote.delivery_total if order.quote else Decimal("0"),
    )


def _flatten_items(order: Any, lang: str) -> list[dict[str, Any]]:
    """The order's lines as one list, with no shop attribution.

    The split across shops is how we source the order, not something the
    customer bought -- they bought one basket from QurBot, and that is what
    their order page shows.
    """
    rows: list[dict[str, Any]] = []
    for part in order.shop_parts:
        for item in part.items:
            product = item.canonical_product
            name = (
                product.name_ru
                if (lang == "ru" and product)
                else (product.name_uz if product else str(item.canonical_id))
            )
            rows.append(
                {
                    "name": name,
                    "qty": item.qty,
                    "unit": item.unit_code,
                    "total": item.line_total,
                }
            )
    return rows
