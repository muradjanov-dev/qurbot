"""One authenticated admin doorway for bot, shop and legacy web actions."""

from __future__ import annotations

import asyncio
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import localized_name
from app.core.admin_redesign_i18n import admin_ui_messages
from app.core.config import settings
from app.core.delivery_format import format_delivery_time
from app.core.fulfillment_ui_i18n import fulfillment_ui_messages
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.conversation import Conversation
from app.db.models.ops import UnmatchedQuery
from app.db.models.order import Order, OrderShopPart
from app.db.models.order_workflow import OrderEvent, OrderNotification
from app.db.models.shop import (
    ProductPhotoBlob,
    Shop,
    ShopProduct,
    ShopProductPriceTier,
)
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db_session
from app.domain.normalize.text import normalize_query
from app.domain.parsing.excel_template import TEMPLATE_FILENAME, build_price_template
from app.services.fx_pricing import FxPricingError, FxPricingService
from app.services.house_shop import is_admin, shop_for_admin
from app.services.order_workflow import OrderWorkflowService, WorkflowError
from app.web.storefront.deps import current_lang, current_user, render, safe_next
from app.web.storefront.pricing import format_money, price_pair
from app.web.storefront.security import require_csrf

router = APIRouter(prefix="/manage", tags=["storefront-manage"])
_MAX_DECIMAL_INPUT_LENGTH = 64


async def _admin(user: User | None = Depends(current_user)) -> User:
    if user is None or user.tg_id is None or not is_admin(user):
        raise HTTPException(403, "admin_required")
    return user


def _admin_page(request: Request, user: User | None, lang: str) -> User | Response:
    """Redirect visitors to login and show a localized denial to customers."""
    if user is None or user.tg_id is None:
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
        target = safe_next(target, "/manage")
        return RedirectResponse(f"/login?next={quote(target, safe='/')}", status_code=303)
    if not is_admin(user):
        return render(request, "permission_denied.html", user=user, lang=lang, status_code=403)
    return user


def _admin_i18n(lang: str) -> dict[str, Any]:
    return {"L": admin_ui_messages(lang)}


def _price_error_key(error: FxPricingError) -> str:
    if error.code == "rate_required":
        return "fx_rate_required"
    if error.code == "currency_change_confirmation_required":
        return "currency_change_confirmation_required"
    if error.code == "invalid_unit":
        return "incompatible_unit"
    if error.code == "invalid_tier":
        return "tier_invalid"
    return "invalid_form"


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
    request: Request,
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
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
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    user = admin
    shop = await _shop(session, user)
    counts = {
        "users": await session.scalar(
            select(func.count(User.id)).where(
                User.tg_id.is_not(None), User.role == "customer", User.is_blocked.is_(False)
            )
        ),
        "products": await session.scalar(select(func.count(CanonicalProduct.id))),
        "offers": await session.scalar(
            select(func.count(ShopProduct.id)).where(
                ShopProduct.shop_id == shop.id, ShopProduct.is_active.is_(True)
            )
        ),
        "orders": await session.scalar(
            select(func.count(Order.id)).where(
                Order.is_test.is_(False),
                Order.status == "new",
            )
        ),
        "gmv": await session.scalar(
            select(func.coalesce(func.sum(Order.grand_total_quoted), 0)).where(
                Order.is_test.is_(False)
            )
        ),
        "unmatched": await session.scalar(select(func.count(UnmatchedQuery.id))),
        "chats": await session.scalar(select(func.count(Conversation.id))),
    }
    recent_orders = (
        (
            await session.execute(
                select(Order.id, Order.contact_name, Order.grand_total_quoted, Order.status)
                .where(
                    Order.is_test.is_(False),
                    exists().where(
                        OrderShopPart.order_id == Order.id, OrderShopPart.shop_id == shop.id
                    ),
                )
                .order_by(Order.created_at.desc(), Order.id.desc())
                .limit(5)
            )
        )
        .mappings()
        .all()
    )
    fx_snapshot = await FxPricingService(session).snapshot()
    return render(
        request,
        "manage.html",
        user=user,
        lang=lang,
        shop=shop,
        counts=counts,
        recent_orders=recent_orders,
        fx_snapshot=fx_snapshot,
        is_super_admin=user.tg_id in settings.super_admin_tg_ids,
        **_admin_i18n(lang),
    )


@router.get("/users")
async def users(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    user = admin
    users = await UserRepository(session).list_recent_users(limit=100)
    return render(
        request, "manage_users.html", user=user, lang=lang, users=users, **_admin_i18n(lang)
    )


@router.get("/admins")
async def admins(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    user = admin
    if user.tg_id not in settings.super_admin_tg_ids:
        return render(request, "permission_denied.html", user=user, lang=lang, status_code=403)
    admins = await UserRepository(session).list_admins()
    return render(
        request, "manage_admins.html", user=user, lang=lang, admins=admins, **_admin_i18n(lang)
    )


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


_WORKFLOW_STATUSES = ("new", "confirmed", "collecting", "in_transit", "fulfilled", "cancelled")
_ORDER_FILTER_STATUSES = (*_WORKFLOW_STATUSES, "partially_fulfilled")
_NORMAL_STATUS_TARGETS: dict[str, tuple[str, ...]] = {
    "new": ("confirmed", "cancelled"),
    "confirmed": ("collecting", "cancelled"),
    "collecting": ("in_transit", "cancelled"),
    "in_transit": ("fulfilled", "cancelled"),
    "fulfilled": (),
    "cancelled": (),
    "partially_fulfilled": (),
}
_ORDER_PAGE_SIZE = 40


def _workflow_error_key(error: WorkflowError) -> str:
    code = error.code.casefold()
    if any(word in code for word in ("stale", "revision", "conflict", "version")):
        return "stale_order"
    if "transition" in code or "terminal" in code or "legacy" in code or "invalid_status" in code:
        return "invalid_transition"
    if "invalid_courier_cost" in code:
        return "invalid_courier_cost"
    if "courier" in code:
        return "courier_required"
    if "reason" in code:
        return "cancel_reason_required"
    return "workflow_error"


def _fulfillment_items(order: Order, lang: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for part in order.shop_parts:
        for item in part.items:
            product = item.canonical_product
            name = (
                localized_name(
                    product.name_uz,
                    product.name_ru,
                    lang,
                    name_uz_cyrl=product.name_uz_cyrl,
                )
                if product
                else str(item.canonical_id)
            )
            rows.append(
                {"name": name, "qty": item.qty, "unit": item.unit_code, "total": item.line_total}
            )
    return rows


async def _render_order_detail(
    request: Request,
    session: AsyncSession,
    order_id: int,
    admin: User,
    lang: str,
    *,
    error_key: str | None = None,
    success_key: str | None = None,
    status_code: int = 200,
) -> Response:
    order = await session.get(Order, order_id)
    if order is None or order.is_test:
        raise HTTPException(404, "order_not_found")
    event_result = await session.execute(
        select(OrderEvent)
        .where(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.created_at, OrderEvent.id)
    )
    notification_result = await session.execute(
        select(OrderNotification)
        .where(OrderNotification.order_id == order.id)
        .order_by(OrderNotification.created_at.desc(), OrderNotification.id.desc())
        .limit(100)
    )
    return render(
        request,
        "manage_order_detail.html",
        user=admin,
        lang=lang,
        order=order,
        items=_fulfillment_items(order, lang),
        events=event_result.scalars().all(),
        notifications=notification_result.scalars().all(),
        normal_targets=_NORMAL_STATUS_TARGETS.get(order.status, ()),
        supported_statuses=_WORKFLOW_STATUSES,
        error_key=error_key,
        success_key=success_key,
        format_delivery_time=format_delivery_time,
        L=fulfillment_ui_messages(lang),
        status_code=status_code,
    )


@router.get("/orders")
async def manage_orders(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
    q: str = Query(default="", max_length=160),
    status: str = Query(default=""),
    problem: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    search = q.strip()
    selected_status = status if status in _ORDER_FILTER_STATUSES else ""
    conditions: list[Any] = [Order.is_test.is_(False)]
    if selected_status:
        conditions.append(Order.status == selected_status)
    if problem:
        conditions.append(Order.delivery_problem.is_(True))
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                cast(Order.id, String).ilike(pattern),
                Order.contact_name.ilike(pattern),
                Order.contact_phone.ilike(pattern),
                Order.delivery_address.ilike(pattern),
                User.full_name.ilike(pattern),
                User.username.ilike(pattern),
            )
        )
    base = select(Order).join(User, User.id == Order.user_id).where(*conditions)
    total = int(
        await session.scalar(
            select(func.count(Order.id)).join(User, User.id == Order.user_id).where(*conditions)
        )
        or 0
    )
    page_count = max(1, (total + _ORDER_PAGE_SIZE - 1) // _ORDER_PAGE_SIZE)
    page = min(page, page_count)
    result = await session.execute(
        base.order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * _ORDER_PAGE_SIZE)
        .limit(_ORDER_PAGE_SIZE)
    )
    orders = result.scalars().all()

    def page_url(target_page: int) -> str:
        params: dict[str, str] = {"page": str(target_page)}
        if search:
            params["q"] = search
        if selected_status:
            params["status"] = selected_status
        if problem:
            params["problem"] = "true"
        return f"/manage/orders?{urlencode(params)}"

    return render(
        request,
        "manage_orders.html",
        user=admin,
        lang=lang,
        orders=orders,
        search=search,
        statuses=_ORDER_FILTER_STATUSES,
        selected_status=selected_status,
        problem_only=problem,
        total=total,
        page=page,
        page_count=page_count,
        page_url=page_url,
        format_delivery_time=format_delivery_time,
        L=fulfillment_ui_messages(lang),
    )


@router.get("/orders/{order_id}")
async def manage_order_detail(
    order_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    notice = request.query_params.get("notice", "")
    known_errors = {
        "stale_order",
        "invalid_transition",
        "workflow_error",
        "cancel_reason_required",
        "courier_required",
    }
    known_successes = {"status_saved", "courier_saved", "note_saved", "notification_queued"}
    return await _render_order_detail(
        request,
        session,
        order_id,
        admin,
        lang,
        error_key=notice if notice in known_errors else None,
        success_key=notice if notice in known_successes else None,
    )


@router.post("/orders/{order_id}/status", dependencies=[Depends(require_csrf)])
async def change_order_status(
    order_id: int,
    request: Request,
    target_status: str = Form(...),
    expected_revision: int = Form(...),
    expected_status: str = Form(...),
    reason: str = Form(default=""),
    correction: bool = Form(default=False),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    try:
        await OrderWorkflowService(session).change_status(
            order_id=order_id,
            actor=admin,
            target=target_status,
            expected_revision=expected_revision,
            expected_status=expected_status,
            reason=reason.strip(),
            correction=correction,
        )
        await session.commit()
    except WorkflowError as error:
        await session.rollback()
        await session.refresh(admin)
        return await _render_order_detail(
            request,
            session,
            order_id,
            admin,
            lang,
            error_key=_workflow_error_key(error),
            status_code=error.status_code,
        )
    return await _render_order_detail(
        request, session, order_id, admin, lang, success_key="status_saved"
    )


@router.post("/orders/{order_id}/courier", dependencies=[Depends(require_csrf)])
async def update_order_courier(
    order_id: int,
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    vehicle: str = Form(default=""),
    cost_uzs: str = Form(default=""),
    expected_revision: int = Form(...),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    cost: Decimal | None = None
    raw_cost = cost_uzs.strip().replace(" ", "").replace(",", ".")
    if raw_cost:
        try:
            cost = Decimal(raw_cost)
        except InvalidOperation:
            cost = Decimal("-1")
        try:
            valid_cost = (
                cost.is_finite()
                and cost >= 0
                and cost.adjusted() < 12
                and cost == cost.quantize(Decimal("0.01"))
            )
        except InvalidOperation:
            valid_cost = False
        if not valid_cost:
            return await _render_order_detail(
                request,
                session,
                order_id,
                admin,
                lang,
                error_key="invalid_courier_cost",
                status_code=422,
            )
    try:
        await OrderWorkflowService(session).update_courier(
            order_id=order_id,
            actor=admin,
            name=name.strip(),
            phone=phone.strip(),
            vehicle=vehicle.strip() or None,
            cost_uzs=cost,
            expected_revision=expected_revision,
        )
        await session.commit()
    except WorkflowError as error:
        await session.rollback()
        await session.refresh(admin)
        return await _render_order_detail(
            request,
            session,
            order_id,
            admin,
            lang,
            error_key=_workflow_error_key(error),
            status_code=error.status_code,
        )
    return await _render_order_detail(
        request, session, order_id, admin, lang, success_key="courier_saved"
    )


@router.post("/orders/{order_id}/note", dependencies=[Depends(require_csrf)])
async def update_order_note(
    order_id: int,
    request: Request,
    note: str = Form(default=""),
    is_problem: bool = Form(default=False),
    expected_revision: int = Form(...),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    try:
        await OrderWorkflowService(session).update_note(
            order_id=order_id,
            actor=admin,
            note=note.strip(),
            is_problem=is_problem,
            expected_revision=expected_revision,
        )
        await session.commit()
    except WorkflowError as error:
        await session.rollback()
        await session.refresh(admin)
        return await _render_order_detail(
            request,
            session,
            order_id,
            admin,
            lang,
            error_key=_workflow_error_key(error),
            status_code=error.status_code,
        )
    return await _render_order_detail(
        request, session, order_id, admin, lang, success_key="note_saved"
    )


@router.post(
    "/orders/{order_id}/notifications/{notification_id}/retry",
    dependencies=[Depends(require_csrf)],
)
async def retry_order_notification(
    order_id: int,
    notification_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    try:
        await OrderWorkflowService(session).retry_notification(
            order_id=order_id,
            notification_id=notification_id,
            actor=admin,
        )
        await session.commit()
    except WorkflowError as error:
        await session.rollback()
        await session.refresh(admin)
        return await _render_order_detail(
            request,
            session,
            order_id,
            admin,
            lang,
            error_key=_workflow_error_key(error),
            status_code=error.status_code,
        )
    return await _render_order_detail(
        request, session, order_id, admin, lang, success_key="notification_queued"
    )


@router.get("/settings")
async def settings_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    shop = await _shop(session, admin)
    return render(
        request,
        "manage_settings.html",
        user=admin,
        lang=lang,
        shop=shop,
        is_super_admin=admin.tg_id in settings.super_admin_tg_ids,
        **_admin_i18n(lang),
    )


async def _currency_settings_page(
    request: Request,
    session: AsyncSession,
    user: User,
    lang: str,
    snapshot: Any,
    *,
    rate_value: str,
    error: str | None,
    status_code: int = 200,
) -> Response:
    updated_admin = None
    if snapshot.updated_by is not None:
        updated_user = await session.get(User, snapshot.updated_by)
        updated_admin = (
            (updated_user.full_name or updated_user.username or str(updated_user.tg_id))
            if updated_user is not None
            else f"#{snapshot.updated_by}"
        )
    return render(
        request,
        "manage_currency.html",
        user=user,
        lang=lang,
        snapshot=snapshot,
        rate_value=rate_value,
        error=error,
        updated_admin=updated_admin,
        status_code=status_code,
        **_admin_i18n(lang),
    )


@router.get("/settings/currency")
async def currency_settings(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    snapshot = await FxPricingService(session).snapshot()
    return await _currency_settings_page(
        request,
        session,
        admin,
        lang,
        snapshot,
        rate_value=str(snapshot.rate) if snapshot.rate is not None else "",
        error=None,
    )


@router.post("/settings/currency", dependencies=[Depends(require_csrf)])
async def publish_currency_rate(
    request: Request,
    rate: str = Form(...),
    expected_revision: int = Form(...),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
    lang: str = Depends(current_lang),
) -> Response:
    amount = _number(rate, positive=True)
    if amount is None:
        snapshot = await FxPricingService(session).snapshot()
        return await _currency_settings_page(
            request,
            session,
            user,
            lang,
            snapshot,
            rate_value=rate,
            error=admin_ui_messages(lang)["fx_rate_invalid"],
            status_code=422,
        )
    try:
        snapshot = await FxPricingService(session).publish_rate(
            amount, admin_id=user.id, expected_revision=expected_revision
        )
    except FxPricingError as exc:
        snapshot = await FxPricingService(session).snapshot()
        error_key = "fx_rate_conflict" if exc.code == "revision_conflict" else "fx_rate_invalid"
        return await _currency_settings_page(
            request,
            session,
            user,
            lang,
            snapshot,
            rate_value=rate,
            error=admin_ui_messages(lang)[error_key],
            status_code=exc.status_code,
        )
    return RedirectResponse("/manage/settings/currency?msg=web_saved", status_code=303)


@router.get("/price-health")
async def price_health(
    request: Request,
    state: str = "all",
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    state = state if state in {"all", "fresh", "aging", "stale"} else "all"
    offers = await ShopRepository(session).list_offers_by_staleness(
        staleness_state=None if state == "all" else state, limit=200
    )
    snapshot = await FxPricingService(session).snapshot()
    rows = []
    for offer in offers:
        source_amount = offer.source_price_per_pack
        if source_amount is None and offer.source_currency == "UZS":
            source_amount = offer.price_per_pack
        pair = price_pair(
            offer.price_per_pack,
            rate_uzs_per_usd=snapshot.rate,
            lang=lang,
            source_currency=offer.source_currency,
            source_amount=source_amount,
        )
        rows.append(
            {
                "offer": offer,
                "prices": pair,
                "source_amount": source_amount,
                "source_amount_label": format_money(source_amount, offer.source_currency, lang),
            }
        )
    return render(
        request,
        "manage_price_health.html",
        user=admin,
        lang=lang,
        offers=rows,
        state=state,
        **_admin_i18n(lang),
    )


@router.post("/price-health/bulk-deactivate", dependencies=[Depends(require_csrf)])
async def bulk_deactivate_stale_offers(
    offer_ids: list[int] = Form(default=[]),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(_admin),
) -> Response:
    await ShopRepository(session).bulk_deactivate_offers(offer_ids)
    return RedirectResponse("/manage/price-health", status_code=303)


def _products_url(page: int, q: str, category_id: int | None, status: str) -> str:
    params: dict[str, str | int] = {"status": status}
    if page > 1:
        params["page"] = page
    if q:
        params["q"] = q
    if category_id is not None:
        params["category_id"] = category_id
    return "/manage/products?" + urlencode(params)


@router.get("/products")
async def products(
    request: Request,
    q: str = "",
    raw_category_id: str | None = Query(default=None, alias="category_id"),
    status: str = "all",
    page: int = 1,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    user = admin
    shop = await _shop(session, user)
    status = status if status in {"all", "available", "unavailable", "archived"} else "all"
    category_id: int | None = None
    if raw_category_id is not None and raw_category_id.strip():
        try:
            category_id = int(raw_category_id.strip())
        except ValueError as exc:
            raise HTTPException(422, "invalid_category_id") from exc
    page_size = settings.web_manage_products_page_size
    filters = []
    if category_id is not None:
        filters.append(CanonicalProduct.category_id == category_id)
    if q.strip():
        term = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(CanonicalProduct.name_uz).like(term),
                func.lower(CanonicalProduct.name_uz_cyrl).like(term),
                func.lower(CanonicalProduct.name_ru).like(term),
                func.lower(CanonicalProduct.slug).like(term),
                func.lower(func.coalesce(CanonicalProduct.brand, "")).like(term),
            )
        )

    has_offer = exists(
        select(ShopProduct.id).where(
            ShopProduct.shop_id == shop.id,
            ShopProduct.canonical_id == CanonicalProduct.id,
            ShopProduct.is_active.is_(True),
            ShopProduct.stock_status != "out",
        )
    )
    available_filter = and_(CanonicalProduct.is_active.is_(True), has_offer)
    unavailable_filter = and_(CanonicalProduct.is_active.is_(True), ~has_offer)
    status_filters = {
        "available": available_filter,
        "unavailable": unavailable_filter,
        "archived": CanonicalProduct.is_active.is_(False),
    }

    async def count_products(extra: Any | None = None) -> int:
        where = [*filters]
        if extra is not None:
            where.append(extra)
        return int(await session.scalar(select(func.count(CanonicalProduct.id)).where(*where)) or 0)

    counts = {
        "all": await count_products(),
        "available": await count_products(available_filter),
        "unavailable": await count_products(unavailable_filter),
        "archived": await count_products(CanonicalProduct.is_active.is_(False)),
    }
    if status in status_filters:
        filters.append(status_filters[status])
    total = counts[status]
    page = max(1, page)
    products_page = (
        await session.scalars(
            select(CanonicalProduct)
            .where(*filters)
            .order_by(CanonicalProduct.name_uz, CanonicalProduct.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    fx_snapshot = await FxPricingService(session).snapshot()
    product_ids = [product.id for product in products_page]
    offers = (
        (
            await session.scalars(
                select(ShopProduct)
                .where(ShopProduct.shop_id == shop.id, ShopProduct.canonical_id.in_(product_ids))
                .order_by(ShopProduct.canonical_id, ShopProduct.pack_size, ShopProduct.id)
            )
        ).all()
        if product_ids
        else []
    )
    offer_map: dict[int, list[ShopProduct]] = {}
    for offer in offers:
        if offer.canonical_id is not None:
            offer_map.setdefault(offer.canonical_id, []).append(offer)

    rows: list[dict[str, Any]] = []
    for product in products_page:
        product_offers = offer_map.get(product.id, [])
        active_offers = [offer for offer in product_offers if offer.is_active]
        primary = next((offer for offer in active_offers if offer.stock_status != "out"), None)
        if primary is None and active_offers:
            primary = active_offers[0]
        if primary is None and product_offers:
            primary = product_offers[0]
        available = product.is_active and any(
            offer.stock_status != "out" for offer in active_offers
        )
        price_labels = None
        if primary is not None:
            source_amount = primary.source_price_per_pack
            if source_amount is None and primary.source_currency == "UZS":
                source_amount = primary.price_per_pack
            pair = price_pair(
                primary.price_per_pack,
                rate_uzs_per_usd=fx_snapshot.rate,
                lang=lang,
                source_currency=primary.source_currency,
                source_amount=source_amount,
            )
            price_labels = {
                **pair,
                "source_amount_label": format_money(source_amount, primary.source_currency, lang),
            }
        rows.append(
            {
                "product": product,
                "display_name": localized_name(
                    product.name_uz, product.name_ru, lang, name_uz_cyrl=product.name_uz_cyrl
                ),
                "image_url": product.display_image_url,
                "offer": primary,
                "offers": product_offers,
                "offer_count": len(active_offers),
                "available": available,
                "status": "archived"
                if not product.is_active
                else ("available" if available else "unavailable"),
                "prices": price_labels,
            }
        )
    categories = (
        await session.scalars(select(Category).order_by(Category.name_uz, Category.id))
    ).all()
    pages = max(1, (total + page_size - 1) // page_size)
    return render(
        request,
        "manage_products.html",
        user=user,
        lang=lang,
        products=rows,
        total=total,
        counts=counts,
        page=page,
        page_size=page_size,
        prev_url=_products_url(page - 1, q, category_id, status),
        next_url=_products_url(page + 1, q, category_id, status),
        status_urls={
            key: _products_url(1, q, category_id, key)
            for key in ("all", "available", "unavailable", "archived")
        },
        q=q,
        category_id=category_id,
        status=status,
        categories=categories,
        pages=pages,
        shop=shop,
        fx_snapshot=fx_snapshot,
        fx_rate_available=fx_snapshot.rate is not None,
        **_admin_i18n(lang),
    )


async def _form_data(session: AsyncSession) -> dict[str, Any]:
    return {
        "categories": (await session.scalars(select(Category).order_by(Category.name_uz))).all(),
        "units": (await session.scalars(select(Unit).order_by(Unit.code))).all(),
    }


async def _new_product_page(
    request: Request,
    session: AsyncSession,
    user: User,
    lang: str,
    shop: Shop,
    *,
    values: Any,
    error: str | None = None,
    candidates: list[CanonicalProduct] | None = None,
    tier_rows: list[dict[str, str]] | None = None,
    status_code: int = 200,
) -> Response:
    snapshot = await FxPricingService(session).snapshot()
    return render(
        request,
        "manage_product_form.html",
        user=user,
        lang=lang,
        product=None,
        offers=[],
        error=error,
        candidates=candidates or [],
        values=values,
        offer_id=None,
        offer_values={},
        tier_rows=tier_rows or [],
        shop=shop,
        fx_rate_available=snapshot.rate is not None,
        status_code=status_code,
        **_admin_i18n(lang),
        **await _form_data(session),
    )


async def _product_page_response(
    request: Request,
    session: AsyncSession,
    user: User,
    lang: str,
    shop: Shop,
    product: CanonicalProduct,
    *,
    error_key: str,
    values: Any,
    status_code: int,
) -> Response:
    offers = (
        await session.scalars(
            select(ShopProduct).where(
                ShopProduct.shop_id == shop.id,
                ShopProduct.canonical_id == product.id,
            )
        )
    ).all()
    snapshot = await FxPricingService(session).snapshot()
    return render(
        request,
        "manage_product_form.html",
        user=user,
        lang=lang,
        product=product,
        offers=offers,
        error=admin_ui_messages(lang)[error_key],
        candidates=[],
        values=values,
        offer_id=None,
        offer_values={},
        tier_rows=[],
        shop=shop,
        fx_snapshot=snapshot,
        fx_rate_available=snapshot.rate is not None,
        status_code=status_code,
        **_admin_i18n(lang),
        **await _form_data(session),
    )


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
    tier_rows: list[dict[str, str]] | None = None,
    error_key: str | None = None,
) -> Response:
    offers = (
        await session.scalars(
            select(ShopProduct).where(
                ShopProduct.shop_id == shop.id,
                ShopProduct.canonical_id == product.id,
            )
        )
    ).all()
    snapshot = await FxPricingService(session).snapshot()
    labels = admin_ui_messages(lang)
    return render(
        request,
        "manage_product_form.html",
        user=user,
        lang=lang,
        product=product,
        offers=offers,
        error=labels[error_key or ("duplicate_product" if duplicate else "invalid_form")],
        candidates=[],
        values={},
        offer_id=offer_id,
        offer_values=offer_values or {},
        tier_rows=tier_rows or [],
        shop=shop,
        fx_rate_available=snapshot.rate is not None,
        status_code=status_code,
        **_admin_i18n(lang),
        **await _form_data(session),
    )


def _tier_form_rows(form: Any) -> list[dict[str, str]]:
    names = (
        "tier_id",
        "tier_min_qty",
        "tier_source_price",
        "tier_currency",
        "tier_currency_confirmed",
    )
    values = {name: form.getlist(name) for name in names}
    size = max((len(items) for items in values.values()), default=0)
    return [
        {
            "tier_id": values["tier_id"][index] if index < len(values["tier_id"]) else "",
            "tier_min_qty": values["tier_min_qty"][index]
            if index < len(values["tier_min_qty"])
            else "",
            "tier_source_price": values["tier_source_price"][index]
            if index < len(values["tier_source_price"])
            else "",
            "tier_currency": values["tier_currency"][index]
            if index < len(values["tier_currency"])
            else "UZS",
            "tier_currency_confirmed": values["tier_currency_confirmed"][index]
            if index < len(values["tier_currency_confirmed"])
            else "",
        }
        for index in range(size)
    ]


async def _sync_price_tiers(
    session: AsyncSession,
    offer: ShopProduct,
    product: CanonicalProduct,
    form: Any,
) -> None:
    rows = _tier_form_rows(form)
    remove_raw = form.getlist("tier_remove_ids")
    existing_tiers = list(
        (
            await session.scalars(
                select(ShopProductPriceTier).where(ShopProductPriceTier.shop_product_id == offer.id)
            )
        ).all()
    )
    existing_by_id = {tier.id: tier for tier in existing_tiers}
    try:
        remove_ids = {int(value) for value in remove_raw if value}
    except ValueError as exc:
        raise HTTPException(422, "invalid_tier") from exc
    if not remove_ids.issubset(existing_by_id):
        raise HTTPException(404, "tier_not_found")
    for remove_id in remove_ids:
        await session.delete(existing_by_id[remove_id])

    submitted_ids = {int(row["tier_id"]) for row in rows if row["tier_id"].isdigit()}
    seen_ids: set[int] = set()
    seen_min_qty = {
        tier.min_qty
        for tier in existing_tiers
        if tier.id not in remove_ids and tier.id not in submitted_ids
    }
    service = FxPricingService(session)
    for row in rows:
        raw_tier_id = row["tier_id"].strip()
        if raw_tier_id and not raw_tier_id.isdigit():
            raise HTTPException(422, "invalid_tier")
        tier_id = int(raw_tier_id) if raw_tier_id else None
        if tier_id in remove_ids:
            continue
        tier = existing_by_id.get(tier_id) if tier_id is not None else None
        min_raw = row["tier_min_qty"].strip()
        amount_raw = row["tier_source_price"].strip()
        if not min_raw and not amount_raw:
            if tier is None:
                continue
            raise FxPricingError("invalid_tier")
        min_qty = _offer_pack_size(min_raw) if min_raw else None
        amount = _number(amount_raw, positive=True) if amount_raw else None
        currency = (
            (row["tier_currency"] or (tier.source_currency if tier else "UZS")).strip().upper()
        )
        if tier_id is not None and (tier is None or tier_id in seen_ids):
            raise HTTPException(404, "tier_not_found")
        if min_qty is None or amount is None or currency not in {"UZS", "USD"}:
            raise FxPricingError("invalid_tier")
        if min_qty in seen_min_qty:
            raise FxPricingError("invalid_tier")
        seen_min_qty.add(min_qty)
        if tier is not None:
            seen_ids.add(tier.id)
            if (
                currency != (tier.source_currency or "UZS")
                and row["tier_currency_confirmed"] != "true"
            ):
                raise FxPricingError("currency_change_confirmation_required")
            source_amount = tier.source_price_per_pack
            if source_amount is None and (tier.source_currency or "UZS") == "UZS":
                source_amount = tier.price_per_pack
            changed = amount != source_amount or currency != (tier.source_currency or "UZS")
            tier.min_qty = min_qty
            if changed:
                await service.set_tier_price(tier, amount, currency)
        else:
            tier = ShopProductPriceTier(
                shop_product_id=offer.id,
                min_qty=min_qty,
                price_per_pack=Decimal("1.00"),
                source_currency="UZS",
            )
            session.add(tier)
            await service.set_tier_price(tier, amount, currency)
    await session.flush()


async def _save_offer(
    session: AsyncSession,
    shop: Shop,
    product: CanonicalProduct,
    *,
    pack_size: str,
    pack_unit_code: str,
    price: str = "",
    source_price: str = "",
    source_currency: str | None = None,
    stock_status: str,
    description: str,
    confirm_currency_change: bool = False,
) -> ShopProduct:
    pack = _offer_pack_size(pack_size)
    raw_amount = source_price.strip() or price.strip()
    amount = _number(raw_amount, positive=True) if raw_amount else None
    if (
        pack is None
        or amount is None
        or len(description) > settings.listing_max_description_len
        or stock_status not in {"in_stock", "low", "on_order", "out"}
        or await session.get(Unit, pack_unit_code) is None
    ):
        raise HTTPException(422, "invalid_offer")
    await FxPricingService(session).snapshot(lock=True)
    existing = await session.scalar(
        select(ShopProduct).where(
            ShopProduct.shop_id == shop.id,
            ShopProduct.canonical_id == product.id,
            ShopProduct.pack_size == pack,
            ShopProduct.pack_unit_code == pack_unit_code,
        )
    )
    currency = (
        (source_currency or (existing.source_currency if existing else "UZS")).strip().upper()
    )
    if existing is None:
        existing = ShopProduct(
            shop_id=shop.id,
            canonical_id=product.id,
            raw_name=product.name_uz,
            raw_unit=pack_unit_code,
            pack_size=pack,
            pack_unit_code=pack_unit_code,
            price_per_pack=Decimal("1.00"),
            price_per_base_unit=Decimal("1.0000"),
            currency="UZS",
            stock_status=stock_status,
            stock_qty=None,
            description=description.strip() or None,
            updated_by="admin",
            is_active=True,
        )
        session.add(existing)
        await FxPricingService(session).set_offer_price(
            existing, amount, currency, product.base_unit_code, updated_by="admin"
        )
    else:
        if currency != existing.source_currency and not confirm_currency_change:
            raise FxPricingError("currency_change_confirmation_required")
        pack_changed = existing.pack_size != pack or existing.pack_unit_code != pack_unit_code
        price_changed = (
            amount != existing.source_price_per_pack
            or currency != existing.source_currency
            or pack_changed
        )
        existing.pack_size = pack
        existing.pack_unit_code = pack_unit_code
        existing.raw_unit = pack_unit_code
        if price_changed:
            await FxPricingService(session).set_offer_price(
                existing, amount, currency, product.base_unit_code, updated_by="admin"
            )
        existing.stock_status = stock_status
        existing.stock_qty = None
        existing.description = description.strip() or None
        existing.is_active = True
    attrs = dict(product.attributes or {})
    attrs.pop("stock_unverified", None)
    attrs.pop("price_on_request", None)
    product.attributes = attrs
    return existing


@router.get("/products/new")
async def new_product(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    user = admin
    shop = await _shop(session, user)
    return await _new_product_page(request, session, user, lang, shop, values={}, error=None)


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
    product_description: str = Form(default=""),
    offer_description: str = Form(default=""),
    price: str = Form(default=""),
    source_price: str = Form(default=""),
    source_currency: str = Form(default="UZS"),
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
    form = await request.form()
    tier_rows = _tier_form_rows(form)
    cleaned = name.strip()
    canonical_description = product_description if "product_description" in form else description
    initial_offer_description = offer_description if "offer_description" in form else description
    create_source_price = source_price.strip() or price.strip()
    create_amount = _number(create_source_price, positive=True) if create_source_price else None
    source_currency = source_currency.strip().upper()
    thick = _number(thickness, positive=True) if thickness.strip() else None
    if (
        not cleaned
        or len(cleaned) > 255
        or len(canonical_description) > settings.listing_max_description_len
        or len(initial_offer_description) > settings.listing_max_description_len
        or (thickness.strip() and thick is None)
        or await session.get(Category, category_id) is None
        or await session.get(Unit, unit_code) is None
    ):
        return await _new_product_page(
            request,
            session,
            user,
            lang,
            shop,
            values=form,
            tier_rows=tier_rows,
            error=admin_ui_messages(lang)["invalid_form"],
            status_code=422,
        )
    if create_source_price:
        create_pack = _offer_pack_size(pack_size)
        create_unit = pack_unit_code or unit_code
        if (
            create_pack is None
            or create_amount is None
            or source_currency not in {"UZS", "USD"}
            or await session.get(Unit, create_unit) is None
        ):
            return await _new_product_page(
                request,
                session,
                user,
                lang,
                shop,
                values=form,
                tier_rows=tier_rows,
                error=admin_ui_messages(lang)["invalid_form"],
                status_code=422,
            )
        snapshot = await FxPricingService(session).snapshot()
        if source_currency == "USD" and snapshot.rate is None:
            return await _new_product_page(
                request,
                session,
                user,
                lang,
                shop,
                values=form,
                tier_rows=tier_rows,
                error=admin_ui_messages(lang)["fx_rate_required"],
                status_code=422,
            )
    elif any(row["tier_min_qty"].strip() or row["tier_source_price"].strip() for row in tier_rows):
        return await _new_product_page(
            request,
            session,
            user,
            lang,
            shop,
            values=form,
            tier_rows=tier_rows,
            error=admin_ui_messages(lang)["invalid_form"],
            status_code=422,
        )
    await FxPricingService(session).snapshot(lock=True)
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
        return await _new_product_page(
            request,
            session,
            user,
            lang,
            shop,
            values=form,
            candidates=similar,
            tier_rows=tier_rows,
            error=admin_ui_messages(lang)["duplicate_product"],
            status_code=409,
        )
    attributes: dict[str, object] = {"stock_unverified": True, "price_on_request": True}
    if size.strip():
        attributes["size"] = size.strip().lower()
    if thick is not None:
        attributes["thickness_mm"] = str(thick)
    if canonical_description.strip():
        attributes["description"] = canonical_description.strip()
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
    nested = await session.begin_nested()
    session.add(product)
    try:
        await session.flush()
    except IntegrityError as exc:
        await nested.rollback()
        raise HTTPException(409, "duplicate_product") from exc
    product.image_url = await _photo(session, photo, shop.id)
    if create_source_price:
        try:
            offer = await _save_offer(
                session,
                shop,
                product,
                pack_size=pack_size,
                pack_unit_code=pack_unit_code or unit_code,
                source_price=create_source_price,
                source_currency=source_currency,
                stock_status=stock_status,
                description=initial_offer_description,
            )
            await _sync_price_tiers(session, offer, product, form)
        except FxPricingError as exc:
            await nested.rollback()
            await session.refresh(user)
            await session.refresh(shop)
            return await _new_product_page(
                request,
                session,
                user,
                lang,
                shop,
                values=form,
                tier_rows=tier_rows,
                error=admin_ui_messages(lang)[_price_error_key(exc)],
                status_code=exc.status_code,
            )
        except HTTPException as exc:
            await nested.rollback()
            await session.refresh(user)
            await session.refresh(shop)
            return await _new_product_page(
                request,
                session,
                user,
                lang,
                shop,
                values=form,
                tier_rows=tier_rows,
                error=admin_ui_messages(lang)["offer_invalid"],
                status_code=exc.status_code,
            )
    await nested.commit()
    return RedirectResponse(f"/manage/products/{product.id}", status_code=303)


@router.get("/products/{product_id}")
async def product_detail(
    product_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    admin = _admin_page(request, user, lang)
    if isinstance(admin, Response):
        return admin
    user = admin
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
    fx_snapshot = await FxPricingService(session).snapshot()
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
        tier_rows=[],
        shop=shop,
        fx_snapshot=fx_snapshot,
        fx_rate_available=fx_snapshot.rate is not None,
        **_admin_i18n(lang),
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
    form = await request.form()
    p = await session.get(CanonicalProduct, product_id)
    if p is None:
        raise HTTPException(404)
    if (
        await session.get(Category, category_id) is None
        or await session.get(Unit, unit_code) is None
    ):
        return await _product_page_response(
            request,
            session,
            user,
            lang,
            shop,
            p,
            error_key="invalid_form",
            values=form,
            status_code=422,
        )
    if unit_code != p.base_unit_code:
        linked = await session.scalar(
            select(ShopProduct.id).where(ShopProduct.canonical_id == product_id).limit(1)
        )
        if linked is not None:
            return await _product_page_response(
                request,
                session,
                user,
                lang,
                shop,
                p,
                error_key="invalid_form",
                values=form,
                status_code=409,
            )
    thick = _number(thickness, positive=True) if thickness.strip() else None
    if not name.strip() or len(name.strip()) > 255 or (thickness.strip() and thick is None):
        return await _product_page_response(
            request,
            session,
            user,
            lang,
            shop,
            p,
            error_key="invalid_form",
            values=form,
            status_code=422,
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
        return await _product_page_response(
            request,
            session,
            user,
            lang,
            shop,
            p,
            error_key="duplicate_product",
            values=form,
            status_code=409,
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
    price: str = Form(default=""),
    source_price: str = Form(default=""),
    source_currency: str = Form(default=""),
    confirm_currency_change: str = Form(default=""),
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
    await FxPricingService(session).snapshot(lock=True)
    offer = await session.get(ShopProduct, offer_id)
    if offer is None or offer.shop_id != shop.id:
        raise HTTPException(404)
    form = await request.form()
    offer_values = {key: str(value) for key, value in form.items()}
    tier_rows = _tier_form_rows(form)
    raw_amount = source_price.strip() or price.strip()
    amount = _number(raw_amount, positive=True) if raw_amount else None
    currency = source_currency.strip().upper() if source_currency.strip() else offer.source_currency
    submitted_pack = bool(pack_size.strip())
    pack = _offer_pack_size(pack_size) if submitted_pack else None
    if currency != offer.source_currency and confirm_currency_change != "true":
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
            tier_rows=tier_rows,
            error_key="currency_change_confirmation_required",
        )
    if (
        amount is None
        or (submitted_pack and pack is None)
        or len(description) > settings.listing_max_description_len
        or stock_status not in {"in_stock", "low", "on_order", "out"}
        or currency not in {"UZS", "USD"}
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
            tier_rows=tier_rows,
            error_key="offer_invalid",
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
            tier_rows=tier_rows,
            error_key="offer_invalid",
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
            tier_rows=tier_rows,
        )
    nested = await session.begin_nested()
    old_source_amount = offer.source_price_per_pack
    if old_source_amount is None and offer.source_currency == "UZS":
        old_source_amount = offer.price_per_pack
    price_changed = (
        amount != old_source_amount
        or currency != offer.source_currency
        or offer.pack_size != new_pack
        or offer.pack_unit_code != new_unit
    )
    offer.pack_size = new_pack
    offer.pack_unit_code = new_unit
    offer.raw_unit = new_unit
    if price_changed:
        try:
            await FxPricingService(session).set_offer_price(
                offer, amount, currency, product.base_unit_code, updated_by="admin"
            )
        except FxPricingError as exc:
            await nested.rollback()
            await session.refresh(user)
            await session.refresh(shop)
            await session.refresh(product)
            return await _product_form_error(
                request,
                session,
                user,
                lang,
                shop,
                product,
                offer_id=offer_id,
                offer_values=offer_values,
                tier_rows=tier_rows,
                error_key=_price_error_key(exc),
                status_code=exc.status_code,
            )
    try:
        await _sync_price_tiers(session, offer, product, form)
    except (FxPricingError, HTTPException) as exc:
        await nested.rollback()
        await session.refresh(user)
        await session.refresh(shop)
        await session.refresh(product)
        if isinstance(exc, FxPricingError):
            error_key = _price_error_key(exc)
            status_code = exc.status_code
        else:
            error_key = "tier_invalid"
            status_code = exc.status_code
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            offer_id=offer_id,
            offer_values=offer_values,
            tier_rows=tier_rows,
            error_key=error_key,
            status_code=status_code,
        )
    offer.stock_status = stock_status
    offer.stock_qty = None
    offer.description = description.strip() or None
    offer.is_active = active
    await session.flush()
    await nested.commit()
    return RedirectResponse(f"/manage/products/{product.id}", status_code=303)


@router.post("/products/{product_id}/offers", dependencies=[Depends(require_csrf)])
async def create_offer(
    product_id: int,
    request: Request,
    pack_size: str = Form(...),
    pack_unit_code: str = Form(...),
    price: str = Form(default=""),
    source_price: str = Form(default=""),
    source_currency: str = Form(default="UZS"),
    confirm_currency_change: str = Form(default=""),
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
    form = await request.form()
    offer_values = {key: str(value) for key, value in form.items()}
    tier_rows = _tier_form_rows(form)
    nested = await session.begin_nested()
    try:
        offer = await _save_offer(
            session,
            shop,
            product,
            pack_size=pack_size,
            pack_unit_code=pack_unit_code,
            price=price,
            source_price=source_price,
            source_currency=source_currency if "source_currency" in form else None,
            confirm_currency_change=confirm_currency_change == "true",
            stock_status=stock_status,
            description=description,
        )
        await _sync_price_tiers(session, offer, product, form)
    except (HTTPException, FxPricingError) as exc:
        await nested.rollback()
        await session.refresh(user)
        await session.refresh(shop)
        await session.refresh(product)
        if isinstance(exc, FxPricingError):
            status_code = exc.status_code
            error_key = _price_error_key(exc)
        else:
            status_code = exc.status_code
            error_key = "offer_invalid"
        return await _product_form_error(
            request,
            session,
            user,
            lang,
            shop,
            product,
            status_code=status_code,
            offer_values=offer_values,
            tier_rows=tier_rows,
            error_key=error_key,
        )
    await nested.commit()
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
