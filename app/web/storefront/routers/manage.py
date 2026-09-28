"""One authenticated admin doorway for bot, shop and legacy web actions."""

from __future__ import annotations

import asyncio
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DomainException
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.ops import UnmatchedQuery
from app.db.models.order import Order
from app.db.models.shop import PriceHistory, ProductPhotoBlob, Shop, ShopProduct
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db_session
from app.domain.normalize.text import normalize_query
from app.domain.parsing.excel_template import TEMPLATE_FILENAME, build_price_template
from app.domain.pricing.units import unit_price
from app.services.house_shop import is_admin, shop_for_admin
from app.web.storefront.deps import current_lang, current_user, render
from app.web.storefront.security import require_csrf

router = APIRouter(prefix="/manage", tags=["storefront-manage"])
_MAX_DECIMAL_INPUT_LENGTH = 64


async def _admin(user: User | None = Depends(current_user)) -> User:
    if user is None or user.tg_id is None or not is_admin(user):
        raise HTTPException(403, "admin_required")
    return user


async def _shop(session: AsyncSession, user: User) -> Shop:
    shop = await shop_for_admin(user, session)
    if shop is None:
        raise HTTPException(403, "shop_required")
    return shop


def _number(raw: str, *, positive: bool = False) -> Decimal | None:
    cleaned = raw.strip()
    if len(cleaned) > _MAX_DECIMAL_INPUT_LENGTH:
        return None
    try:
        value = Decimal(cleaned.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        return None
    if not value.is_finite() or (positive and value <= 0) or value < 0:
        return None
    return value


def _fits_numeric(value: Decimal, *, precision: int, scale: int) -> bool:
    """Whether PostgreSQL can store the rounded value in NUMERIC(p, s)."""
    if not value.is_finite() or value <= 0:
        return False
    if value.adjusted() >= precision - scale:
        return False
    quantum = Decimal(1).scaleb(-scale)
    maximum = Decimal(10) ** (precision - scale) - quantum
    try:
        rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return False
    return Decimal("0") < rounded <= maximum


def _offer_price(raw: str) -> Decimal | None:
    value = _number(raw, positive=True)
    if value is None or not _fits_numeric(value, precision=14, scale=2):
        return None
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _offer_pack_size(raw: str) -> Decimal | None:
    value = _number(raw, positive=True)
    if value is None or not _fits_numeric(value, precision=14, scale=4):
        return None
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _offer_base_price(value: Decimal) -> bool:
    return _fits_numeric(value, precision=14, scale=4)


def _identity_slug(
    category_id: int,
    unit_code: str,
    name: str,
    size: str,
    thickness: Decimal | None,
    brand: str,
) -> str:
    identity = json.dumps(
        [
            category_id,
            unit_code,
            normalize_query(name).text_norm,
            size.strip().lower(),
            str(thickness) if thickness is not None else "",
            brand.strip().casefold(),
        ],
        ensure_ascii=False,
    )
    return f"admin-{sha256(identity.encode()).hexdigest()}"


def _same_variant(
    product: CanonicalProduct,
    *,
    unit_code: str,
    name: str,
    size: str,
    thickness: Decimal | None,
    brand: str,
) -> bool:
    attributes = product.attributes or {}
    return (
        normalize_query(product.name_uz).text_norm == normalize_query(name).text_norm
        and product.base_unit_code == unit_code
        and attributes.get("size", "") == size.strip().lower()
        and str(attributes.get("thickness_mm", "")) == (str(thickness) if thickness else "")
        and (product.brand or "").casefold() == brand.strip().casefold()
    )


def _search_document(name: str, name_cyrl: str, name_ru: str, brand: str, size: str) -> str:
    return " ".join(
        dict.fromkeys(
            normalize_query(value).text_norm
            for value in (name, name_cyrl, name_ru, brand, size)
            if value.strip()
        )
    )


async def _photo(session: AsyncSession, upload: UploadFile | None, shop_id: int) -> str | None:
    if upload is None or not upload.filename:
        return None
    payload = await upload.read(settings.web_max_upload_bytes + 1)
    mime = upload.content_type or ""
    signatures = {
        "image/jpeg": payload.startswith(b"\xff\xd8\xff"),
        "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": payload[8:12] == b"WEBP" and payload[:4] == b"RIFF",
    }
    if not payload or len(payload) > settings.web_max_upload_bytes or not signatures.get(mime):
        raise HTTPException(422, "invalid_photo")
    unique = "web-" + sha256(payload).hexdigest()
    blob = await session.scalar(
        select(ProductPhotoBlob).where(ProductPhotoBlob.file_unique_id == unique)
    )
    if blob is None:
        blob = ProductPhotoBlob(
            file_unique_id=unique,
            file_id=unique,
            shop_id=shop_id,
            mime_type=mime,
            byte_size=len(payload),
            data=payload,
        )
        session.add(blob)
        await session.flush()
    return f"/manage/photo/{unique}"


@router.get("/photo/{unique}")
async def product_photo(unique: str, session: AsyncSession = Depends(get_db_session)) -> Response:
    path = f"/manage/photo/{unique}"
    product = await session.scalar(
        select(CanonicalProduct.id).where(
            CanonicalProduct.image_url == path, CanonicalProduct.is_active.is_(True)
        )
    )
    if product is None:
        raise HTTPException(404)
    blob = await session.scalar(
        select(ProductPhotoBlob).where(ProductPhotoBlob.file_unique_id == unique)
    )
    if blob is None:
        raise HTTPException(404)
    return StreamingResponse(BytesIO(blob.data), media_type=blob.mime_type)


@router.get("/import-template")
async def download_import_template(
    user: User = Depends(_admin), lang: str = Depends(current_lang)
) -> Response:
    payload = await asyncio.to_thread(build_price_template, lang)
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_FILENAME}"'},
    )


@router.get("")
async def home(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _shop(session, user)
    counts = {
        "users": await session.scalar(select(func.count(User.id))),
        "products": await session.scalar(select(func.count(CanonicalProduct.id))),
        "offers": await session.scalar(
            select(func.count(ShopProduct.id)).where(ShopProduct.is_active.is_(True))
        ),
        "orders": await session.scalar(
            select(func.count(Order.id)).where(Order.is_test.is_(False))
        ),
        "gmv": await session.scalar(
            select(func.coalesce(func.sum(Order.grand_total_quoted), 0)).where(
                Order.is_test.is_(False)
            )
        ),
        "unmatched": await session.scalar(select(func.count(UnmatchedQuery.id))),
    }
    return render(
        request,
        "manage.html",
        user=user,
        lang=lang,
        shop=shop,
        counts=counts,
        is_super_admin=user.tg_id in settings.super_admin_tg_ids,
    )


@router.get("/users")
async def users(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    users = await UserRepository(session).list_recent_users(limit=100)
    return render(request, "manage_users.html", user=user, lang=lang, users=users)


@router.get("/admins")
async def admins(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    if user.tg_id not in settings.super_admin_tg_ids:
        raise HTTPException(403, "super_admin_required")
    admins = await UserRepository(session).list_admins()
    return render(request, "manage_admins.html", user=user, lang=lang, admins=admins)


@router.post("/admins")
async def promote_admin(
    tg_id: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
) -> Response:
    if user.tg_id not in settings.super_admin_tg_ids:
        raise HTTPException(403, "super_admin_required")
    if not tg_id.isdigit() or await UserRepository(session).set_role(int(tg_id), "admin") is None:
        raise HTTPException(422, "user_not_found")
    return RedirectResponse("/manage/admins", status_code=303)


@router.get("/products")
async def products(
    request: Request,
    q: str = "",
    page: int = 1,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    page_size = settings.web_manage_products_page_size
    rows, total = await CatalogRepository(session).admin_list_products(
        search=q or None, offset=(max(1, page) - 1) * page_size, limit=page_size
    )
    return render(
        request,
        "manage_products.html",
        user=user,
        lang=lang,
        products=rows,
        total=total,
        page=max(1, page),
        page_size=page_size,
        q=q,
    )


async def _form_data(session: AsyncSession) -> dict[str, Any]:
    return {
        "categories": (await session.scalars(select(Category).order_by(Category.name_uz))).all(),
        "units": (await session.scalars(select(Unit).order_by(Unit.code))).all(),
    }


async def _product_form_error(
    request: Request,
    session: AsyncSession,
    user: User,
    lang: str,
    shop: Shop,
    product: CanonicalProduct,
    *,
    duplicate: bool = False,
    status_code: int = 422,
    offer_id: int | None = None,
    offer_values: dict[str, str] | None = None,
) -> Response:
    offers = (
        await session.scalars(
            select(ShopProduct).where(
                ShopProduct.shop_id == shop.id,
                ShopProduct.canonical_id == product.id,
            )
        )
    ).all()
    return render(
        request,
        "manage_product_form.html",
        user=user,
        lang=lang,
        product=product,
        offers=offers,
        error=t("manage_duplicate" if duplicate else "manage_invalid", lang=lang),
        candidates=[],
        values={},
        offer_id=offer_id,
        offer_values=offer_values or {},
        status_code=status_code,
        **await _form_data(session),
    )


async def _save_offer(
    session: AsyncSession,
    shop: Shop,
    product: CanonicalProduct,
    *,
    pack_size: str,
    pack_unit_code: str,
    price: str,
    stock_status: str,
    description: str,
) -> None:
    pack, amount = _offer_pack_size(pack_size), _offer_price(price)
    if (
        pack is None
        or amount is None
        or len(description) > settings.listing_max_description_len
        or stock_status not in {"in_stock", "low", "on_order", "out"}
        or await session.get(Unit, pack_unit_code) is None
    ):
        raise HTTPException(422, "invalid_offer")
    try:
        base_price = unit_price(amount, pack, pack_unit_code, product.base_unit_code)
    except DomainException as exc:
        raise HTTPException(422, "incompatible_unit") from exc
    if not _offer_base_price(base_price):
        raise HTTPException(422, "invalid_offer")
    existing = await session.scalar(
        select(ShopProduct).where(
            ShopProduct.shop_id == shop.id,
            ShopProduct.canonical_id == product.id,
            ShopProduct.pack_size == pack,
            ShopProduct.pack_unit_code == pack_unit_code,
        )
    )
    if existing is None:
        existing = ShopProduct(
            shop_id=shop.id,
            canonical_id=product.id,
            raw_name=product.name_uz,
            raw_unit=pack_unit_code,
            pack_size=pack,
            pack_unit_code=pack_unit_code,
            price_per_pack=amount,
            price_per_base_unit=base_price,
            currency="UZS",
            stock_status=stock_status,
            stock_qty=None,
            description=description.strip() or None,
            updated_by="admin",
            is_active=True,
        )
        session.add(existing)
        await session.flush()
        session.add(
            PriceHistory(
                shop_product_id=existing.id,
                price_per_pack=amount,
                price_per_base_unit=base_price,
            )
        )
    else:
        if existing.price_per_pack != amount:
            await ShopRepository(session).update_offer_price(
                existing.id, amount, base_price, "admin"
            )
        existing.stock_status = stock_status
        existing.stock_qty = None
        existing.description = description.strip() or None
        existing.is_active = True
    attrs = dict(product.attributes or {})
    attrs.pop("stock_unverified", None)
    attrs.pop("price_on_request", None)
    product.attributes = attrs


@router.get("/products/new")
async def new_product(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    return render(
        request,
        "manage_product_form.html",
        user=user,
        lang=lang,
        product=None,
        error=None,
        candidates=[],
        values={},
        **await _form_data(session),
    )


@router.post("/products/new", dependencies=[Depends(require_csrf)])
async def create_product(
    request: Request,
    name: str = Form(...),
    name_ru: str = Form(default=""),
    name_uz_cyrl: str = Form(default=""),
    category_id: int = Form(...),
    unit_code: str = Form(...),
    size: str = Form(default=""),
    thickness: str = Form(default=""),
    brand: str = Form(default=""),
    description: str = Form(default=""),
    price: str = Form(default=""),
    pack_size: str = Form(default="1"),
    pack_unit_code: str = Form(default=""),
    stock_status: str = Form(default="out"),
    force_new: bool = Form(default=False),
    photo: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _shop(session, user)
    cleaned = name.strip()
    thick = _number(thickness, positive=True) if thickness.strip() else None
    if (
        not cleaned
        or len(cleaned) > 255
        or len(description) > settings.listing_max_description_len
        or (thickness.strip() and thick is None)
        or await session.get(Category, category_id) is None
        or await session.get(Unit, unit_code) is None
    ):
        return render(
            request,
            "manage_product_form.html",
            user=user,
            lang=lang,
            product=None,
            error=t("manage_invalid", lang=lang),
            candidates=[],
            values=await request.form(),
            status_code=422,
            **await _form_data(session),
        )
    if price.strip():
        create_pack = _offer_pack_size(pack_size)
        create_price = _offer_price(price)
        create_unit = pack_unit_code or unit_code
        if (
            create_pack is None
            or create_price is None
            or await session.get(Unit, create_unit) is None
        ):
            return render(
                request,
                "manage_product_form.html",
                user=user,
                lang=lang,
                product=None,
                error=t("manage_invalid", lang=lang),
                candidates=[],
                values=await request.form(),
                status_code=422,
                **await _form_data(session),
            )
        try:
            base_price = unit_price(create_price, create_pack, create_unit, unit_code)
        except DomainException:
            base_price = None
        if (
            create_pack is None
            or create_price is None
            or base_price is None
            or not _offer_base_price(base_price)
        ):
            return render(
                request,
                "manage_product_form.html",
                user=user,
                lang=lang,
                product=None,
                error=t("manage_invalid", lang=lang),
                candidates=[],
                values=await request.form(),
                status_code=422,
                **await _form_data(session),
            )
    candidates, _ = await CatalogRepository(session).admin_list_products(
        search=cleaned, offset=0, limit=10
    )
    similar = [
        p
        for p, _, _ in candidates
        if p.category_id == category_id
        and (
            normalize_query(p.name_uz).text_norm == normalize_query(cleaned).text_norm
            or (bool(size.strip()) and (p.attributes or {}).get("size") == size.strip().lower())
        )
    ]
    category_products = (
        await session.scalars(
            select(CanonicalProduct).where(CanonicalProduct.category_id == category_id)
        )
    ).all()
    exact = [
        p
        for p in category_products
        if _same_variant(
            p, unit_code=unit_code, name=cleaned, size=size, thickness=thick, brand=brand
        )
    ]
    if exact or (similar and not force_new):
        return render(
            request,
            "manage_product_form.html",
            user=user,
            lang=lang,
            product=None,
            error=t("manage_duplicate", lang=lang),
            candidates=similar,
            values=await request.form(),
            status_code=409,
            **await _form_data(session),
        )
    attributes: dict[str, object] = {"stock_unverified": True, "price_on_request": True}
    if size.strip():
        attributes["size"] = size.strip().lower()
    if thick is not None:
        attributes["thickness_mm"] = str(thick)
    if description.strip():
        attributes["description"] = description.strip()
    product = CanonicalProduct(
        slug=_identity_slug(category_id, unit_code, cleaned, size, thick, brand),
        name_uz=cleaned,
        name_uz_cyrl=name_uz_cyrl.strip() or cleaned,
        name_ru=name_ru.strip() or cleaned,
        brand=brand.strip() or None,
        category_id=category_id,
        base_unit_code=unit_code,
        attributes=attributes,
        source="admin",
        source_ref="web",
        reference_price=None,
        is_active=True,
        search_doc=_search_document(
            cleaned, name_uz_cyrl or cleaned, name_ru or cleaned, brand, size
        ),
    )
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "duplicate_product") from exc
    product.image_url = await _photo(session, photo, shop.id)
    if price.strip():
        await _save_offer(
            session,
            shop,
            product,
            pack_size=pack_size,
            pack_unit_code=pack_unit_code or unit_code,
            price=price,
            stock_status=stock_status,
            description=description,
        )
    return RedirectResponse(f"/manage/products/{product.id}", status_code=303)


@router.get("/products/{product_id}")
async def product_detail(
    product_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _shop(session, user)
    product = await session.get(CanonicalProduct, product_id)
    if product is None:
        raise HTTPException(404)
    offers = (
        await session.scalars(
            select(ShopProduct).where(
                ShopProduct.shop_id == shop.id, ShopProduct.canonical_id == product_id
            )
        )
    ).all()
    return render(
        request,
        "manage_product_form.html",
        user=user,
        lang=lang,
        product=product,
        offers=offers,
        error=None,
        candidates=[],
        values={},
        offer_id=None,
        offer_values={},
        **await _form_data(session),
    )


@router.post("/products/{product_id}", dependencies=[Depends(require_csrf)])
async def edit_product(
    product_id: int,
    request: Request,
    name: str = Form(...),
    name_ru: str = Form(default=""),
    name_uz_cyrl: str = Form(default=""),
    category_id: int = Form(...),
    unit_code: str = Form(...),
    size: str = Form(default=""),
    thickness: str = Form(default=""),
    brand: str = Form(default=""),
    description: str = Form(default=""),
    active: bool = Form(default=False),
    remove_photo: bool = Form(default=False),
    photo: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _shop(session, user)
    p = await session.get(CanonicalProduct, product_id)
    if p is None:
        raise HTTPException(404)
    offers = (
        await session.scalars(
            select(ShopProduct).where(
                ShopProduct.shop_id == shop.id,
                ShopProduct.canonical_id == p.id,
            )
        )
    ).all()
    if (
        await session.get(Category, category_id) is None
        or await session.get(Unit, unit_code) is None
    ):
        return render(
            request,
            "manage_product_form.html",
            user=user,
            lang=lang,
            product=p,
            offers=offers,
            error=t("manage_invalid", lang=lang),
            candidates=[],
            values=await request.form(),
            status_code=422,
            **await _form_data(session),
        )
    if unit_code != p.base_unit_code:
        linked = await session.scalar(
            select(ShopProduct.id).where(ShopProduct.canonical_id == product_id).limit(1)
        )
        if linked is not None:
            return render(
                request,
                "manage_product_form.html",
                user=user,
                lang=lang,
                product=p,
                offers=offers,
                error=t("manage_invalid", lang=lang),
                candidates=[],
                values=await request.form(),
                status_code=409,
                **await _form_data(session),
            )
    thick = _number(thickness, positive=True) if thickness.strip() else None
    if not name.strip() or len(name.strip()) > 255 or (thickness.strip() and thick is None):
        return render(
            request,
            "manage_product_form.html",
            user=user,
            lang=lang,
            product=p,
            offers=offers,
            error=t("manage_invalid", lang=lang),
            candidates=[],
            values=await request.form(),
            status_code=422,
            **await _form_data(session),
        )
    other_products = (
        await session.scalars(
            select(CanonicalProduct).where(
                CanonicalProduct.category_id == category_id, CanonicalProduct.id != product_id
            )
        )
    ).all()
    if any(
        _same_variant(
            other, unit_code=unit_code, name=name, size=size, thickness=thick, brand=brand
        )
        for other in other_products
    ):
        return render(
            request,
            "manage_product_form.html",
            user=user,
            lang=lang,
            product=p,
            offers=offers,
            error=t("manage_duplicate", lang=lang),
            candidates=[],
            values=await request.form(),
            status_code=409,
            **await _form_data(session),
        )
    p.name_uz = name.strip()
    p.name_uz_cyrl = name_uz_cyrl.strip() or p.name_uz
    p.name_ru = name_ru.strip() or p.name_uz
    p.category_id = category_id
    p.base_unit_code = unit_code
    p.brand = brand.strip() or None
    attrs = dict(p.attributes or {})
    attrs.update(
        size=size.strip().lower(),
        thickness_mm=str(thick) if thick else "",
        description=description.strip(),
    )
    p.attributes = attrs
    p.is_active = active
    p.source = "admin"
    if p.slug.startswith("admin-"):
        p.slug = _identity_slug(category_id, unit_code, p.name_uz, size, thick, brand)
    p.search_doc = _search_document(p.name_uz, p.name_uz_cyrl, p.name_ru, brand, size)
    new_photo = await _photo(session, photo, shop.id)
    if new_photo:
        p.image_url = new_photo
        attrs = dict(p.attributes or {})
        attrs.pop("image_hidden", None)
        p.attributes = attrs
    elif remove_photo:
        p.image_url = None
        attrs = dict(p.attributes or {})
        attrs["image_hidden"] = True
        p.attributes = attrs
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "duplicate_product") from exc
    return RedirectResponse(f"/manage/products/{product_id}", status_code=303)


@router.post("/offers/{offer_id}", dependencies=[Depends(require_csrf)])
async def edit_offer(
    offer_id: int,
    request: Request,
    price: str = Form(...),
    stock_status: str = Form(...),
    pack_size: str = Form(default=""),
    pack_unit_code: str = Form(default=""),
    description: str = Form(default=""),
    active: bool = Form(default=False),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _shop(session, user)
    offer = await session.get(ShopProduct, offer_id)
    amount = _offer_price(price)
    submitted_pack = bool(pack_size.strip())
    pack = _offer_pack_size(pack_size) if submitted_pack else None
    offer_values = {key: str(value) for key, value in (await request.form()).items()}
    if offer is None or offer.shop_id != shop.id:
        raise HTTPException(404)
    if (
        amount is None
        or (submitted_pack and pack is None)
        or len(description) > settings.listing_max_description_len
        or stock_status not in {"in_stock", "low", "on_order", "out"}
    ):
        if offer.canonical_id is None:
            raise HTTPException(422, "invalid_offer")
        product = await session.get(CanonicalProduct, offer.canonical_id)
        if product is None:
            raise HTTPException(404)
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            offer_id=offer.id,
            offer_values=offer_values,
        )
    product = await session.get(CanonicalProduct, offer.canonical_id)
    if product is None or offer.pack_unit_code is None:
        raise HTTPException(422, "invalid_offer")
    new_pack = pack if pack is not None else offer.pack_size
    new_unit = pack_unit_code.strip() or offer.pack_unit_code
    unit = await session.get(Unit, new_unit)
    if new_pack <= 0 or unit is None:
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            offer_id=offer.id,
            offer_values=offer_values,
        )
    duplicate = await session.scalar(
        select(ShopProduct.id).where(
            ShopProduct.shop_id == shop.id,
            ShopProduct.canonical_id == product.id,
            ShopProduct.pack_size == new_pack,
            ShopProduct.pack_unit_code == new_unit,
            ShopProduct.id != offer.id,
        )
    )
    if duplicate is not None:
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            duplicate=True,
            status_code=409,
            offer_id=offer.id,
            offer_values=offer_values,
        )
    try:
        base_price = unit_price(amount, new_pack, new_unit, product.base_unit_code)
    except DomainException:
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            offer_id=offer.id,
            offer_values=offer_values,
        )
    if not _offer_base_price(base_price):
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            offer_id=offer.id,
            offer_values=offer_values,
        )
    if (
        offer.price_per_pack != amount
        or offer.pack_size != new_pack
        or offer.pack_unit_code != new_unit
    ):
        await ShopRepository(session).update_offer_price(offer.id, amount, base_price, "admin")
    offer.pack_size = new_pack
    offer.pack_unit_code = new_unit
    offer.raw_unit = new_unit
    offer.stock_status = stock_status
    offer.stock_qty = None
    offer.description = description.strip() or None
    offer.is_active = active
    await session.flush()
    return RedirectResponse(f"/manage/products/{product.id}", status_code=303)


@router.post("/products/{product_id}/offers", dependencies=[Depends(require_csrf)])
async def create_offer(
    product_id: int,
    request: Request,
    pack_size: str = Form(...),
    pack_unit_code: str = Form(...),
    price: str = Form(...),
    stock_status: str = Form(...),
    description: str = Form(default=""),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    shop = await _shop(session, user)
    product = await session.get(CanonicalProduct, product_id)
    if product is None:
        raise HTTPException(404)
    offer_values = {key: str(value) for key, value in (await request.form()).items()}
    try:
        await _save_offer(
            session,
            shop,
            product,
            pack_size=pack_size,
            pack_unit_code=pack_unit_code,
            price=price,
            stock_status=stock_status,
            description=description,
        )
    except HTTPException as exc:
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            duplicate=exc.status_code == 409,
            status_code=exc.status_code,
            offer_values=offer_values,
        )
    except DomainException:
        return await _product_form_error(
            request, session, user, lang, shop, product, offer_values=offer_values
        )
    return RedirectResponse(f"/manage/products/{product_id}", status_code=303)


@router.post("/products/{product_id}/archive", dependencies=[Depends(require_csrf)])
async def archive_product(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
) -> Response:
    product = await session.get(CanonicalProduct, product_id)
    if product is None:
        raise HTTPException(404)
    product.is_active = False
    await session.flush()
    return RedirectResponse("/manage/products", status_code=303)


@router.post("/products/{product_id}/restore", dependencies=[Depends(require_csrf)])
async def restore_product(
    product_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
) -> Response:
    product = await session.get(CanonicalProduct, product_id)
    if product is None:
        raise HTTPException(404)
    product.is_active = True
    await session.flush()
    return RedirectResponse(f"/manage/products/{product_id}", status_code=303)
