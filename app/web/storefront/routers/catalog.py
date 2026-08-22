"""Browsing the catalogue: sections, product lists, one product's card."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_catalog_price, format_uzs
from app.core.config import settings
from app.core.i18n import t
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import get_db_session
from app.web.storefront.deps import current_lang, current_user, render

router = APIRouter(tags=["storefront"])


def _category_name(category: object, lang: str) -> str:
    if lang == "ru":
        return str(getattr(category, "name_ru", ""))
    return str(getattr(category, "name_uz", ""))


def _page_bounds(page: int, total: int) -> tuple[int, int]:
    size = settings.web_catalog_page_size
    pages = max(1, (total + size - 1) // size)
    return min(max(page, 1), pages), pages


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_root(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    categories = await CatalogRepository(session).list_root_categories()
    return render(
        request,
        "catalog.html",
        user=user,
        lang=lang,
        categories=categories,
        category=None,
    )


@router.get("/catalog/all", response_class=HTMLResponse)
async def catalog_all(
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    """Everything we carry, a page at a time.

    Browsing by section assumes the customer knows which section their product
    lives in. Paging through the whole catalogue is the shorter path when they
    only want to see what is stocked and what it costs.
    """
    return await _render_products(
        request,
        session,
        user=user,
        lang=lang,
        page=page,
        category=None,
        category_ids=None,
        title=t("web_catalog_title", lang=lang),
    )


@router.get("/catalog/{category_id}", response_class=HTMLResponse)
async def catalog_category(
    category_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    repo = CatalogRepository(session)
    category = await repo.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="category_not_found")

    children = await repo.list_child_categories(category_id)
    if children:
        return render(
            request,
            "catalog.html",
            user=user,
            lang=lang,
            categories=children,
            category=category,
        )

    return await _render_products(
        request,
        session,
        user=user,
        lang=lang,
        page=page,
        category=category,
        category_ids=await repo.get_category_subtree_ids(category_id),
        title=_category_name(category, lang),
    )


async def _render_products(
    request: Request,
    session: AsyncSession,
    *,
    user: User | None,
    lang: str,
    page: int,
    category: object | None,
    category_ids: list[int] | None,
    title: str,
) -> HTMLResponse:
    repo = CatalogRepository(session)
    size = settings.web_catalog_page_size

    _, total = await repo.list_catalog_page(offset=0, limit=1, category_ids=category_ids)
    page, pages = _page_bounds(page, total)
    rows, _ = await repo.list_catalog_page(
        offset=(page - 1) * size, limit=size, category_ids=category_ids
    )

    products = [
        {
            "id": product.id,
            "name": product.name_ru if lang == "ru" else product.name_uz,
            "brand": product.brand,
            "unit": product.base_unit_code,
            "price": format_catalog_price(live_price, product.reference_price, lang=lang),
        }
        for product, live_price in rows
    ]
    return render(
        request,
        "products.html",
        user=user,
        lang=lang,
        title=title,
        category=category,
        products=products,
        page=page,
        pages=pages,
    )


@router.get("/product/{canonical_id}", response_class=HTMLResponse)
async def product_detail(
    canonical_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    """One product's card.

    Says nothing about which shops carry it or how many: the customer is buying
    from us, so the supply side is not their concern.
    """
    repo = CatalogRepository(session)
    product = await repo.get(canonical_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="product_not_found")

    offers = await ShopRepository(session).get_active_offers_for_canonicals([canonical_id])
    prices = [offer.price_per_pack for offer in offers]
    currency = t("web_currency", lang=lang)
    if prices:
        low, high = min(prices), max(prices)
        price_label = (
            f"{format_uzs(low)} {currency}"
            if low == high
            else f"{format_uzs(low)} – {format_uzs(high)} {currency}"
        )
    else:
        price_label = format_catalog_price(None, product.reference_price, lang=lang)

    return render(
        request,
        "product.html",
        user=user,
        lang=lang,
        product=product,
        product_name=product.name_ru if lang == "ru" else product.name_uz,
        price_label=price_label,
        has_live_offer=bool(prices),
        cheapest=min(prices) if prices else Decimal("0"),
    )
