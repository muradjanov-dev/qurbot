"""Browsing the catalogue: sections, product lists, one product's card."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from decimal import Decimal
from urllib.parse import parse_qsl, quote, unquote_plus, urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import format_qty, localized_name
from app.core.config import settings
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct, Category
from app.db.models.shop import ShopProduct
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import get_db_session
from app.domain.catalog_images import category_photo_filename
from app.domain.normalize.translit import latin_to_cyrillic_uz
from app.services.fx_pricing import FxPricingService
from app.web.storefront.deps import current_lang, current_user, render
from app.web.storefront.pricing import format_money, price_pair

router = APIRouter(tags=["storefront"])
CATALOG_PATH = re.compile(r"/catalog(?:/all|/[1-9][0-9]*)?\Z")


def _catalog_return(raw: str | None, fallback: str) -> str:
    """Accept only local catalogue paths and the filter keys we generate."""
    if not raw or "\\" in raw or any(ord(char) < 32 for char in raw):
        return fallback
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or parsed.fragment or not CATALOG_PATH.fullmatch(parsed.path):
        return fallback
    params = parse_qsl(parsed.query, keep_blank_values=True)
    if len({key for key, _ in params}) != len(params):
        return fallback
    for key, value in params:
        if key == "page":
            if not re.fullmatch(r"[1-9][0-9]*", value):
                return fallback
        elif key == "q":
            if len(value) > 100 or any(ord(char) < 32 for char in value):
                return fallback
        else:
            return fallback
    return raw


def _image_url(product: CanonicalProduct, offers: list[ShopProduct]) -> str:
    identity = json.dumps(
        [
            product.image_url,
            product.attributes.get("image_hidden"),
            product.name_uz,
            product.category_id,
            [(offer.id, offer.photos) for offer in offers if offer.canonical_id == product.id],
        ],
        sort_keys=True,
    )
    version = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return f"/media/product/{product.id}?v={version}"


def _needs_confirmation(product: CanonicalProduct, live_price: Decimal | None) -> bool:
    attributes = product.attributes or {}
    return (
        live_price is None
        and product.reference_price is None
        or bool(attributes.get("price_on_request"))
        or bool(attributes.get("stock_unverified"))
    )


def _category_name(category: object, lang: str) -> str:
    if lang == "ru":
        return str(getattr(category, "name_ru", ""))
    name = str(getattr(category, "name_uz", ""))
    return latin_to_cyrillic_uz(name) if lang == "uz_cyrl" else name


def _category_views(categories: Sequence[Category], lang: str) -> list[dict[str, object]]:
    return [
        {
            "id": category.id,
            "name": _category_name(category, lang),
            "slug": category.slug,
            "image_src": f"/static/store/images/{category_photo_filename(category.slug)}",
        }
        for category in categories
    ]


def _page_bounds(page: int, total: int) -> tuple[int, int]:
    size = settings.web_catalog_page_size
    pages = max(1, (total + size - 1) // size)
    return min(max(page, 1), pages), pages


def _page_url(path: str, page: int, search: str | None) -> str:
    params: list[tuple[str, str]] = []
    if page > 1:
        params.append(("page", str(page)))
    if search:
        params.append(("q", search))
    return path + ("?" + urlencode(params) if params else "")


def _return_url(request: Request, page: int, search: str | None) -> str:
    """Keep the visible query-string order so scroll restoration hits its key."""
    kept: list[str] = []
    seen: set[str] = set()
    for part in request.url.query.split("&"):
        if not part:
            continue
        key = unquote_plus(part.partition("=")[0])
        if key == "fragment":
            continue
        if key not in {"page", "q"} or key in seen:
            return _page_url(str(request.url.path), page, search)
        seen.add(key)
        kept.append(part)
    return str(request.url.path) + ("?" + "&".join(kept) if kept else "")


def _pack_label(offer: ShopProduct | None, product: CanonicalProduct, lang: str) -> str:
    if offer is None:
        base_unit = product.base_unit
        unit_name = (
            (base_unit.name_ru if lang == "ru" else base_unit.name_uz)
            if base_unit
            else product.base_unit_code
        )
        return f"1 {unit_name}"
    pack_unit = offer.pack_unit
    unit_name = (
        (pack_unit.name_ru if lang == "ru" else pack_unit.name_uz)
        if pack_unit
        else (offer.pack_unit_code or offer.raw_unit)
    )
    return f"{format_qty(offer.pack_size.normalize())} {unit_name}"


def _product_view(
    product: CanonicalProduct,
    offer: ShopProduct | None,
    *,
    lang: str,
    rate: Decimal | None,
    href: str,
    image_src: str,
) -> dict[str, object]:
    live_price = offer.price_per_pack if offer else None
    needs_confirmation = _needs_confirmation(product, live_price)
    amount = live_price if live_price is not None else product.reference_price
    pair = price_pair(
        amount,
        rate_uzs_per_usd=rate,
        lang=lang,
        source_currency=offer.source_currency if offer else "UZS",
        source_amount=offer.source_price_per_pack if offer else None,
    )
    return {
        "id": product.id,
        "href": href,
        "image_src": image_src,
        "name": localized_name(
            product.name_uz, product.name_ru, lang, name_uz_cyrl=product.name_uz_cyrl
        ),
        "category_id": product.category_id,
        "category_name": _category_name(product.category, lang),
        "description": (product.attributes or {}).get("description"),
        "brand": product.brand,
        "unit": product.base_unit_code,
        "pack_label": _pack_label(offer, product, lang),
        "price_uzs": pair["price_uzs"],
        "price_usd": pair["price_usd"],
        "price_uzs_label": (
            t("web_product_confirm_required", lang=lang)
            if needs_confirmation
            else ("~ " if live_price is None else "") + format_money(pair["price_uzs"], "UZS", lang)
        ),
        "price_usd_label": pair["price_usd_label"] if not needs_confirmation else None,
        "price_usd_approximate": pair["price_usd_approximate"],
        "price_source_currency": pair["price_source_currency"],
        "available": product.is_active,
        "needs_confirmation": needs_confirmation,
    }


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_root(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None, alias="q", max_length=100),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    search = (search or "").strip() or None
    if search:
        return await _render_products(
            request,
            session,
            user=user,
            lang=lang,
            page=page,
            category=None,
            category_ids=None,
            title=t("store_ui_search_results", lang=lang),
            search=search,
        )
    categories = await CatalogRepository(session).list_root_categories()
    return render(
        request,
        "catalog.html",
        user=user,
        lang=lang,
        categories=_category_views(categories, lang),
        category=None,
    )


@router.get("/catalog/all", response_class=HTMLResponse)
async def catalog_all(
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None, alias="q", max_length=100),
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
        search=(search or "").strip() or None,
    )


@router.get("/catalog/{category_id}", response_class=HTMLResponse)
async def catalog_category(
    category_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    search: str | None = Query(None, alias="q", max_length=100),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    repo = CatalogRepository(session)
    category = await repo.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="category_not_found")

    children = await repo.list_child_categories(category_id)
    search = (search or "").strip() or None
    if children and not search:
        return render(
            request,
            "catalog.html",
            user=user,
            lang=lang,
            categories=_category_views(children, lang),
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
        search=search,
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
    search: str | None = None,
) -> HTMLResponse:
    repo = CatalogRepository(session)
    size = settings.web_catalog_page_size
    fx = await FxPricingService(session).snapshot(lock=True)

    _, total = await repo.list_catalog_page(
        offset=0, limit=1, category_ids=category_ids, search=search
    )
    page, pages = _page_bounds(page, total)
    rows, _ = await repo.list_catalog_page(
        offset=(page - 1) * size, limit=size, category_ids=category_ids, search=search
    )

    offers = await ShopRepository(session).get_active_offers_for_canonicals(
        [product.id for product, _ in rows]
    )
    best_offers: dict[int, ShopProduct] = {}
    for offer in offers:
        if offer.canonical_id is not None:
            current = best_offers.get(offer.canonical_id)
            if current is None or (offer.price_per_pack, offer.id) < (
                current.price_per_pack,
                current.id,
            ):
                best_offers[offer.canonical_id] = offer

    return_path = _return_url(request, page, search)
    products = [
        _product_view(
            product,
            best_offers.get(product.id),
            lang=lang,
            rate=fx.rate,
            href=f"/product/{product.id}?from={quote(return_path, safe='')}",
            image_src=_image_url(product, list(offers)),
        )
        for product, _ in rows
    ]
    categories = _category_views(await repo.list_root_categories(), lang)
    return render(
        request,
        "fragments/products.html"
        if request.query_params.get("fragment") == "1"
        else "products.html",
        user=user,
        lang=lang,
        title=title,
        category=category,
        categories=categories,
        products=products,
        total=total,
        search=search or "",
        page=page,
        pages=pages,
        previous_url=_page_url(str(request.url.path), page - 1, search) if page > 1 else None,
        next_url=_page_url(str(request.url.path), page + 1, search) if page < pages else None,
        fx_revision=fx.revision,
    )


@router.get("/product/{canonical_id}", response_class=HTMLResponse)
async def product_detail(
    canonical_id: int,
    request: Request,
    from_catalog: str | None = Query(None, alias="from"),
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
    if product is None or (not product.is_active and request.query_params.get("fragment") != "1"):
        raise HTTPException(status_code=404, detail="product_not_found")

    fx = await FxPricingService(session).snapshot(lock=True)
    offers = await ShopRepository(session).get_active_offers_for_canonicals([canonical_id])
    best_offer = min(offers, key=lambda offer: (offer.price_per_pack, offer.id), default=None)
    prices = [offer.price_per_pack for offer in offers]
    live_price = best_offer.price_per_pack if best_offer else None
    needs_confirmation = _needs_confirmation(product, live_price)
    amount = live_price if live_price is not None else product.reference_price
    pair = price_pair(
        amount,
        rate_uzs_per_usd=fx.rate,
        lang=lang,
        source_currency=best_offer.source_currency if best_offer else "UZS",
        source_amount=best_offer.source_price_per_pack if best_offer else None,
    )
    if needs_confirmation:
        price_label = t("web_product_confirm_required", lang=lang)
    elif amount is not None:
        price_label = ("~ " if live_price is None else "") + format_money(amount, "UZS", lang)
    else:
        price_label = t("web_product_confirm_required", lang=lang)

    return render(
        request,
        "fragments/product.html" if request.query_params.get("fragment") == "1" else "product.html",
        user=user,
        lang=lang,
        product=product,
        image_src=_image_url(product, list(offers)),
        return_to=_catalog_return(from_catalog, f"/catalog/{product.category_id}"),
        restore_position=bool(
            from_catalog
            and _catalog_return(from_catalog, f"/catalog/{product.category_id}") == from_catalog
        ),
        product_name=localized_name(
            product.name_uz, product.name_ru, lang, name_uz_cyrl=product.name_uz_cyrl
        ),
        price_label=price_label,
        has_live_offer=bool(prices),
        needs_confirmation=needs_confirmation,
        cheapest=min(prices) if prices else Decimal("0"),
        price_uzs=pair["price_uzs"],
        price_uzs_label=price_label,
        price_usd=pair["price_usd"] if not needs_confirmation else None,
        price_usd_label=pair["price_usd_label"] if not needs_confirmation else None,
        price_usd_approximate=pair["price_usd_approximate"],
        pack_label=_pack_label(best_offer, product, lang),
        fx_revision=fx.revision,
    )
