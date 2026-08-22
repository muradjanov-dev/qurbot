"""The shop owner's portal: prices, stock, delivery terms, orders, imports.

Same actions the Telegram shop panel offers, on a screen wide enough to work
through a price list. Every route re-checks that this account manages this shop:
ids arrive from the client, and without that check anyone could accept another
shop's orders by editing a URL.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainException
from app.core.logging import get_logger
from app.db.models.shop import Shop, ShopProduct
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.order_repo import OrderRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import get_db_session
from app.domain.pricing.units import unit_price
from app.services.supplier_service import SupplierService
from app.web.storefront.deps import current_lang, current_user, render

logger = get_logger(__name__)

router = APIRouter(prefix="/shop", tags=["storefront-shop"])

STOCK_STATUSES = ("in_stock", "low", "on_order", "out")


async def _require_shop(session: AsyncSession, user: User | None, shop_id: int) -> Shop:
    """The shop, if this account manages it. Anything else is a 404."""
    if user is None or user.tg_id is None:
        raise HTTPException(status_code=404, detail="shop_not_found")
    shops = await ShopRepository(session).list_shops_for_owner(user.tg_id)
    for shop in shops:
        if shop.id == shop_id:
            return shop
    raise HTTPException(status_code=404, detail="shop_not_found")


def _decimal_or_none(raw: str) -> Decimal | None:
    text = raw.strip().replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value >= 0 else None


@router.get("")
async def shop_root(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    if user is None:
        return RedirectResponse("/login?next=/shop", status_code=303)

    shops = await ShopRepository(session).list_shops_for_owner(user.tg_id)
    if len(shops) == 1:
        return RedirectResponse(f"/shop/{shops[0].id}", status_code=303)
    return render(request, "shop_list.html", user=user, lang=lang, shops=shops)


@router.get("/{shop_id}")
async def shop_panel(
    shop_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    _, total = await ShopRepository(session).get_shop_products_paginated(shop.id, 0, 1)
    pending = await OrderRepository(session).count_pending_parts_for_shop(shop.id)
    return render(
        request,
        "shop_panel.html",
        user=user,
        lang=lang,
        shop=shop,
        product_count=total,
        pending_orders=pending,
    )


@router.get("/{shop_id}/products")
async def shop_products(
    shop_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    size = settings.web_shop_products_page_size
    products, total = await ShopRepository(session).get_shop_products_paginated(
        shop.id, (page - 1) * size, size
    )
    pages = max(1, (total + size - 1) // size)
    return render(
        request,
        "shop_products.html",
        user=user,
        lang=lang,
        shop=shop,
        products=products,
        page=min(page, pages),
        pages=pages,
        stock_statuses=STOCK_STATUSES,
    )


@router.post("/{shop_id}/products/{product_id}")
async def update_product(
    shop_id: int,
    product_id: int,
    price: str = Form(default=""),
    stock_status: str = Form(default=""),
    page: int = Form(default=1),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    """Update one offer's price and availability.

    A price change also writes `price_history` and resets staleness, which is
    what `update_offer_price` is for -- doing it by hand here would quietly
    skip the audit trail the trust score is computed from.
    """
    shop = await _require_shop(session, user, shop_id)
    repo = ShopRepository(session)

    offer = await session.get(ShopProduct, product_id)
    if offer is None or offer.shop_id != shop.id:
        raise HTTPException(status_code=404, detail="offer_not_found")

    new_price = _decimal_or_none(price)
    if new_price is not None and new_price != offer.price_per_pack:
        await repo.update_offer_price(
            shop_product_id=offer.id,
            price_per_pack=new_price,
            price_per_base_unit=_per_base_unit(offer, new_price),
            updated_by="shop",
        )

    if stock_status in STOCK_STATUSES:
        offer.stock_status = stock_status
        await session.flush()

    return RedirectResponse(
        f"/shop/{shop_id}/products?page={max(1, page)}&msg=web_shop_updated",
        status_code=303,
    )


def _per_base_unit(offer: object, price: Decimal) -> Decimal:
    """Price per base unit for a new pack price.

    Falls back to a plain division when the units are not comparable (an offer
    imported with a unit the catalogue does not define): a slightly coarse
    per-unit price still sorts sensibly, whereas refusing the edit would leave
    the owner unable to correct a wrong price at all.
    """
    pack_size = getattr(offer, "pack_size", Decimal("1")) or Decimal("1")
    pack_unit = getattr(offer, "pack_unit_code", None)
    canonical = getattr(offer, "canonical_product", None)
    base_unit = getattr(canonical, "base_unit_code", None) if canonical else None

    if pack_unit and base_unit:
        try:
            return unit_price(price, pack_size, pack_unit, base_unit)
        except DomainException:
            logger.info("web_shop_unit_price_fallback", pack_unit=pack_unit, base_unit=base_unit)
    return price / pack_size if pack_size > 0 else price


@router.get("/{shop_id}/orders")
async def shop_orders(
    shop_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    parts = await OrderRepository(session).list_parts_for_shop(shop.id)
    return render(request, "shop_orders.html", user=user, lang=lang, shop=shop, parts=parts)


@router.post("/{shop_id}/orders/{part_id}/{decision}")
async def respond_to_order(
    shop_id: int,
    part_id: int,
    decision: str,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    if decision not in ("accept", "reject"):
        raise HTTPException(status_code=404, detail="unknown_decision")

    repo = OrderRepository(session)
    part = await repo.get_shop_part(part_id)
    if part is None or part.shop_id != shop.id:
        raise HTTPException(status_code=404, detail="order_part_not_found")

    response = "accepted" if decision == "accept" else "rejected"
    await repo.update_shop_response(part.id, response)
    part.status = response
    await session.flush()
    return RedirectResponse(f"/shop/{shop_id}/orders?msg=web_shop_updated", status_code=303)


@router.get("/{shop_id}/delivery")
async def shop_delivery(
    shop_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    repo = ShopRepository(session)
    return render(
        request,
        "shop_delivery.html",
        user=user,
        lang=lang,
        shop=shop,
        rules=await repo.get_shop_delivery_rules(shop.id),
        districts=await repo.list_districts(),
    )


@router.post("/{shop_id}/delivery")
async def save_delivery_rule(
    shop_id: int,
    district_id: str = Form(default=""),
    fee: str = Form(default="0"),
    free_above: str = Form(default=""),
    min_order: str = Form(default="0"),
    eta_hours: int = Form(default=24),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    await ShopRepository(session).upsert_delivery_rule(
        shop_id=shop.id,
        district_id=int(district_id) if district_id.strip().isdigit() else None,
        fee=_decimal_or_none(fee) or Decimal("0"),
        free_above=_decimal_or_none(free_above),
        min_order=_decimal_or_none(min_order) or Decimal("0"),
        eta_hours=max(1, eta_hours),
    )
    return RedirectResponse(f"/shop/{shop_id}/delivery?msg=web_shop_updated", status_code=303)


def _supplier_service(session: AsyncSession) -> SupplierService:
    return SupplierService(
        ShopRepository(session), CatalogRepository(session), OpsRepository(session)
    )


@router.get("/{shop_id}/import")
async def shop_import(
    shop_id: int,
    request: Request,
    batch: int | None = Query(default=None),
    row: int | None = Query(default=None),
    q: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    """Upload form, plus the staged batch waiting for confirmation.

    Nothing here writes to `shop_products`: a batch only reaches live prices
    through the explicit "apply" below (SPEC §6, the import invariant).
    """
    shop = await _require_shop(session, user, shop_id)
    service = _supplier_service(session)

    summary = None
    unmatched: list[object] = []
    candidates: list[object] = []
    if batch is not None:
        stored = await ShopRepository(session).get_import_batch(batch)
        if stored is None or stored.shop_id != shop.id:
            raise HTTPException(status_code=404, detail="batch_not_found")
        summary = await service.get_batch_summary(batch)
        unmatched = list(await ShopRepository(session).get_unmatched_import_rows(batch))
        if row is not None and q.strip():
            candidates = list(
                await CatalogRepository(session).search_canonical_products(q.strip(), limit=8)
            )

    return render(
        request,
        "shop_import.html",
        user=user,
        lang=lang,
        shop=shop,
        summary=summary,
        batch_id=batch,
        unmatched=unmatched,
        active_row=row,
        query=q,
        candidates=candidates,
    )


@router.post("/{shop_id}/import")
async def upload_price_file(
    shop_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)

    payload = await file.read()
    if len(payload) > settings.web_max_upload_bytes:
        return RedirectResponse(
            f"/shop/{shop_id}/import?msg=web_shop_import_too_big", status_code=303
        )

    try:
        summary = await _supplier_service(session).process_file_upload(
            shop_id=shop.id,
            file_bytes=payload,
            filename=file.filename or "prices.xlsx",
        )
    except (DomainException, ValueError) as exc:
        logger.warning("web_price_import_failed", shop_id=shop.id, error=str(exc))
        return RedirectResponse(
            f"/shop/{shop_id}/import?msg=web_shop_import_bad_file", status_code=303
        )

    return RedirectResponse(f"/shop/{shop_id}/import?batch={summary.batch_id}", status_code=303)


async def _require_batch_row(session: AsyncSession, shop: Shop, batch_id: int, row_id: int) -> None:
    repo = ShopRepository(session)
    batch = await repo.get_import_batch(batch_id)
    if batch is None or batch.shop_id != shop.id:
        raise HTTPException(status_code=404, detail="batch_not_found")
    if not any(candidate.id == row_id for candidate in await repo.get_import_rows(batch_id)):
        raise HTTPException(status_code=404, detail="row_not_found")


@router.post("/{shop_id}/import/{batch_id}/rows/{row_id}/resolve")
async def resolve_import_row(
    shop_id: int,
    batch_id: int,
    row_id: int,
    canonical_id: int = Form(...),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    await _require_batch_row(session, shop, batch_id, row_id)
    await _supplier_service(session).resolve_row(row_id, canonical_id)
    return RedirectResponse(f"/shop/{shop_id}/import?batch={batch_id}", status_code=303)


@router.post("/{shop_id}/import/{batch_id}/rows/{row_id}/skip")
async def skip_import_row(
    shop_id: int,
    batch_id: int,
    row_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    await _require_batch_row(session, shop, batch_id, row_id)
    await _supplier_service(session).skip_row(row_id)
    return RedirectResponse(f"/shop/{shop_id}/import?batch={batch_id}", status_code=303)


@router.post("/{shop_id}/import/{batch_id}/apply")
async def apply_import(
    shop_id: int,
    batch_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    batch = await ShopRepository(session).get_import_batch(batch_id)
    if batch is None or batch.shop_id != shop.id:
        raise HTTPException(status_code=404, detail="batch_not_found")

    result = await _supplier_service(session).apply_batch(batch_id)
    return RedirectResponse(
        f"/shop/{shop_id}/import?msg=web_shop_import_applied&n={result.applied_count}",
        status_code=303,
    )


@router.post("/{shop_id}/import/{batch_id}/cancel")
async def cancel_import(
    shop_id: int,
    batch_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    shop = await _require_shop(session, user, shop_id)
    batch = await ShopRepository(session).get_import_batch(batch_id)
    if batch is None or batch.shop_id != shop.id:
        raise HTTPException(status_code=404, detail="batch_not_found")

    await _supplier_service(session).cancel_batch(batch_id)
    return RedirectResponse(f"/shop/{shop_id}/import?msg=web_shop_updated", status_code=303)
