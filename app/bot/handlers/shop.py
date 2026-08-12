import re
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, ContentType, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import (
    get_import_batch_keyboard,
    get_product_list_keyboard,
    get_shop_order_decision_keyboard,
    get_unmatched_row_keyboard,
)
from app.bot.states import ShopOwnerStates
from app.core.i18n import t
from app.db.models.order import OrderShopPart
from app.db.models.shop import Shop, ShopProduct
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.services.catalog_service import CatalogService
from app.services.supplier_service import SupplierService

router = Router(name="shop")


# ---------------------------------------------------------------------------
# Helper: get shop for user
# ---------------------------------------------------------------------------


async def _get_user_shop(user: User, session: AsyncSession) -> Shop | None:
    stmt = select(Shop).where(Shop.owner_tg_id == user.tg_id)
    res = await session.execute(stmt)
    return res.scalars().first()


# ---------------------------------------------------------------------------
# Shop Portal Entry
# ---------------------------------------------------------------------------


@router.message(F.text.in_(["🏪 Do'kon paneli", "🏪 Дўкон панели", "🏪 Панель магазина"]))
async def menu_shop_portal(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        await message.answer(t("not_shop_owner", lang=lang))
        return

    shop = await _get_user_shop(user, session)
    shop_name = shop.name if shop else "Do'koningiz"
    panel_text = (
        f"{t('shop_panel_title', lang=lang, shop_name=shop_name)}\n\n"
        "Quyidagi amallardan birini tanlang:\n"
        "• <b>Tez narx yangilash:</b> <code>cement m400 52000</code> shaklida yozing\n"
        "• <b>Narxlarni yuklash:</b> Excel/CSV faylni yuboring\n"
        "• <b>Mahsulotlarim:</b> /shop_products\n"
        "• <b>Yetkazish sozlamalari:</b> /delivery_rules\n"
        "• <b>Yangi buyurtmalar:</b> /shop_orders"
    )
    await message.answer(panel_text)


# ---------------------------------------------------------------------------
# Shop Orders
# ---------------------------------------------------------------------------


@router.message(F.text.startswith("/shop_orders"))
async def cmd_shop_orders(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        return

    shop = await _get_user_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    part_stmt = select(OrderShopPart).where(
        OrderShopPart.shop_id == shop.id,
        OrderShopPart.status == "pending",
    )
    part_res = await session.execute(part_stmt)
    pending_parts = list(part_res.scalars().all())

    if not pending_parts:
        await message.answer("Yangi kutilayotgan buyurtmalar yo'q.")
        return

    for part in pending_parts:
        lines_text = "\n".join(
            f"• Mahsulot #{item.canonical_id} — {item.qty:g} {item.unit_code} "
            f"({item.line_total:,.0f} so'm)"
            for item in part.items
        )
        total_sum = part.subtotal + part.delivery_fee
        msg_text = (
            f"🔔 <b>Yangi buyurtma #{part.order_id} (Qism #{part.id})</b>\n\n"
            f"{lines_text}\n\n"
            f"Jami: <b>{total_sum:,.0f} so'm</b> "
            f"(Mahsulotlar: {part.subtotal:,.0f} + Yetkazish: {part.delivery_fee:,.0f})"
        )
        await message.answer(msg_text, reply_markup=get_shop_order_decision_keyboard(part.id))


@router.callback_query(F.data.startswith("shop_order:"))
async def callback_shop_order_decision(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not callback.data:
        return
    parts = callback.data.split(":")
    action = parts[1]  # accept or reject
    part_id = int(parts[2])

    order_part = await session.get(OrderShopPart, part_id)
    if not order_part:
        if isinstance(callback.message, Message):
            await callback.message.answer("Buyurtma topilmadi.")
        return

    if action == "accept":
        order_part.status = "accepted"
        msg_text = f"✅ Buyurtma #{order_part.order_id} (Qism #{part_id}) qabul qilindi!"
    else:
        order_part.status = "rejected"
        msg_text = f"❌ Buyurtma #{order_part.order_id} (Qism #{part_id}) rad etildi."

    await session.commit()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(msg_text)


# ---------------------------------------------------------------------------
# Quick Price Update
# ---------------------------------------------------------------------------

# One-liner regex: e.g. "cement m400 52000" or "g'isht 1400"
QUICK_PRICE_REGEX = re.compile(
    r"^(.*?)\s+(\d+(?:[.,]\d+)?)\s*(?:so'?m|sum|сум|uzs)?$", re.IGNORECASE
)


@router.message(ShopOwnerStates.waiting_for_quick_price)
@router.message(lambda msg: bool(msg.text and QUICK_PRICE_REGEX.match(msg.text.strip())))
async def handle_quick_price_update(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        return
    if not message.text:
        return

    match = QUICK_PRICE_REGEX.match(message.text.strip())
    if not match:
        return

    prod_phrase, price_str = match.groups()
    price_val = Decimal(price_str.replace(",", "."))

    # Match product against catalog
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    catalog_service = CatalogService(catalog_repo, ops_repo)

    parsed = await catalog_service.parse_and_match_basket(prod_phrase)
    if not parsed:
        await message.answer("Mahsulot nomi aniqlanmadi.")
        return

    _, decision = parsed[0]
    canonical_id = decision.canonical_id
    if not canonical_id and decision.candidates:
        canonical_id = decision.candidates[0].canonical_id

    if not canonical_id:
        await message.answer(f"«{prod_phrase}» katalogda topilmadi.")
        return

    # Find or create shop product
    shop = await _get_user_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    shop_repo = ShopRepository(session)
    p_stmt = select(ShopProduct).where(
        ShopProduct.shop_id == shop.id,
        ShopProduct.canonical_id == canonical_id,
    )
    p_res = await session.execute(p_stmt)
    shop_prod = p_res.scalars().first()

    if shop_prod:
        await shop_repo.update_offer_price(
            shop_product_id=shop_prod.id,
            price_per_pack=price_val,
            price_per_base_unit=price_val / shop_prod.pack_size
            if shop_prod.pack_size > Decimal("0")
            else price_val,
            updated_by="shop",
        )
    else:
        shop_prod = ShopProduct(
            shop_id=shop.id,
            canonical_id=canonical_id,
            raw_name=prod_phrase,
            raw_unit="dona",
            pack_size=Decimal("1"),
            price_per_pack=price_val,
            price_per_base_unit=price_val,
            stock_status="in_stock",
            is_active=True,
            staleness_state="fresh",
            updated_by="shop",
        )
        session.add(shop_prod)

    await session.commit()

    prod_name = decision.candidates[0].name_uz if decision.candidates else prod_phrase
    await message.answer(
        t("price_updated_success", lang=lang, product_name=prod_name, price=f"{price_val:,.0f}")
    )


# ---------------------------------------------------------------------------
# Excel/CSV File Upload
# ---------------------------------------------------------------------------


@router.message(F.content_type == ContentType.DOCUMENT)
async def handle_document_upload(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Handle Excel/CSV document uploads from shop owners."""
    if user.role not in ("shop_owner", "admin"):
        return
    if not message.document:
        return

    filename = message.document.file_name or "unknown"
    lower_name = filename.lower()
    if not lower_name.endswith((".xlsx", ".xls", ".csv")):
        return

    shop = await _get_user_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    # Send immediate acknowledgment
    status_msg = await message.answer(t("upload_processing", lang=lang))

    # Download file
    bot = message.bot
    if not bot:
        return
    file = await bot.get_file(message.document.file_id)
    if not file or not file.file_path:
        await status_msg.edit_text("Faylni yuklab bo'lmadi.")
        return

    file_data = await bot.download_file(file.file_path)
    if not file_data:
        await status_msg.edit_text("Faylni yuklab bo'lmadi.")
        return

    file_bytes = file_data.read()

    # Process through supplier service
    shop_repo = ShopRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    supplier_svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    summary = await supplier_svc.process_file_upload(
        shop_id=shop.id,
        file_bytes=file_bytes,
        filename=filename,
    )

    await session.commit()

    # Show summary with confirmation buttons
    summary_text = t(
        "batch_summary",
        lang=lang,
        total=summary.total_rows,
        auto_count=summary.auto_matched,
        manual_count=summary.needs_review,
        skipped=summary.skipped,
    )

    await status_msg.edit_text(
        summary_text,
        reply_markup=get_import_batch_keyboard(
            batch_id=summary.batch_id,
            auto_count=summary.auto_matched,
            manual_count=summary.needs_review,
            lang=lang,
        ),
    )


# ---------------------------------------------------------------------------
# Import Batch Callbacks
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("import_confirm:"))
async def callback_confirm_batch(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data:
        return
    batch_id = int(callback.data.split(":")[1])

    shop_repo = ShopRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    supplier_svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    result = await supplier_svc.apply_batch(batch_id)
    await session.commit()

    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("batch_applied", lang=lang, count=result.applied_count))


@router.callback_query(F.data.startswith("import_cancel:"))
async def callback_cancel_batch(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data:
        return
    batch_id = int(callback.data.split(":")[1])

    shop_repo = ShopRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    supplier_svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    await supplier_svc.cancel_batch(batch_id)
    await session.commit()

    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("batch_cancelled", lang=lang))


@router.callback_query(F.data.startswith("import_review:"))
async def callback_review_batch(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    """Show the first unmatched row for manual resolution."""
    if not callback.data:
        return
    batch_id = int(callback.data.split(":")[1])

    shop_repo = ShopRepository(session)
    unmatched = await shop_repo.get_unmatched_import_rows(batch_id)

    if not unmatched:
        if isinstance(callback.message, Message):
            await callback.message.edit_text("Barcha qatorlar moslashtirilgan!")
        return

    row = unmatched[0]
    raw_name = row.raw_payload.get("raw_name", "?")

    # Find candidates for this product
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    catalog_service = CatalogService(catalog_repo, ops_repo)

    candidates: list[tuple[int, str, float]] = []
    try:
        results = await catalog_service.parse_and_match_basket(raw_name)
        if results:
            _, decision = results[0]
            for c in decision.candidates[:5]:
                candidates.append((c.canonical_id, c.name_uz, float(c.score)))
    except Exception:
        pass

    text = (
        f"⚠️ <b>Moslashtirilmagan qator #{row.row_no}:</b>\n\n"
        f"«{raw_name}»\n\n"
        f"Quyidagilardan birini tanlang ({len(unmatched)} ta qoldi):"
    )

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=get_unmatched_row_keyboard(row.id, candidates, lang=lang),
        )


@router.callback_query(F.data.startswith("import_resolve:"))
async def callback_resolve_import_row(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    """Resolve an import row to a canonical product."""
    if not callback.data:
        return
    parts = callback.data.split(":")
    row_id = int(parts[1])
    canonical_id = int(parts[2])

    shop_repo = ShopRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    supplier_svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    await supplier_svc.resolve_row(row_id, canonical_id)

    # Find the batch for this row to show next unmatched
    from app.db.models.shop import ImportRow

    row = await session.get(ImportRow, row_id)
    if row:
        # Get canonical name
        from app.db.models.catalog import CanonicalProduct

        canon = await session.get(CanonicalProduct, canonical_id)
        canon_name = canon.name_uz if canon else f"#{canonical_id}"

        raw_name = row.raw_payload.get("raw_name", "?")
        if isinstance(callback.message, Message):
            await callback.message.answer(
                t("import_row_resolved", lang=lang, name=raw_name, canonical_name=canon_name)
            )

        # Show next unmatched row
        unmatched = await shop_repo.get_unmatched_import_rows(row.batch_id)
        if unmatched:
            next_row = unmatched[0]
            next_raw = next_row.raw_payload.get("raw_name", "?")
            candidates: list[tuple[int, str, float]] = []
            try:
                catalog_service = CatalogService(catalog_repo, ops_repo)
                results = await catalog_service.parse_and_match_basket(next_raw)
                if results:
                    _, decision = results[0]
                    for c in decision.candidates[:5]:
                        candidates.append((c.canonical_id, c.name_uz, float(c.score)))
            except Exception:
                pass

            text = (
                f"⚠️ <b>Moslashtirilmagan qator #{next_row.row_no}:</b>\n\n"
                f"«{next_raw}»\n\n"
                f"Quyidagilardan birini tanlang ({len(unmatched)} ta qoldi):"
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    text,
                    reply_markup=get_unmatched_row_keyboard(next_row.id, candidates, lang=lang),
                )
        else:
            # All resolved — show confirm button
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    "✅ Barcha qatorlar moslashtirildi!",
                    reply_markup=get_import_batch_keyboard(
                        batch_id=row.batch_id,
                        auto_count=0,
                        manual_count=0,
                        lang=lang,
                    ),
                )

    await session.commit()


@router.callback_query(F.data.startswith("import_skip:"))
async def callback_skip_import_row(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    """Skip an unmatched import row."""
    if not callback.data:
        return
    row_id = int(callback.data.split(":")[1])

    shop_repo = ShopRepository(session)
    catalog_repo = CatalogRepository(session)
    ops_repo = OpsRepository(session)
    supplier_svc = SupplierService(shop_repo, catalog_repo, ops_repo)

    await supplier_svc.skip_row(row_id)

    from app.db.models.shop import ImportRow

    row = await session.get(ImportRow, row_id)
    if row:
        unmatched = await shop_repo.get_unmatched_import_rows(row.batch_id)
        if unmatched:
            # Show next
            next_row = unmatched[0]
            next_raw = next_row.raw_payload.get("raw_name", "?")
            candidates: list[tuple[int, str, float]] = []
            try:
                catalog_service = CatalogService(catalog_repo, ops_repo)
                results = await catalog_service.parse_and_match_basket(next_raw)
                if results:
                    _, decision = results[0]
                    for c in decision.candidates[:5]:
                        candidates.append((c.canonical_id, c.name_uz, float(c.score)))
            except Exception:
                pass

            text = (
                f"⚠️ <b>Moslashtirilmagan qator #{next_row.row_no}:</b>\n\n"
                f"«{next_raw}»\n\n"
                f"Quyidagilardan birini tanlang ({len(unmatched)} ta qoldi):"
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    text,
                    reply_markup=get_unmatched_row_keyboard(next_row.id, candidates, lang=lang),
                )
        else:
            if isinstance(callback.message, Message):
                await callback.message.edit_text(
                    "✅ Barcha qatorlar ko'rib chiqildi!",
                    reply_markup=get_import_batch_keyboard(
                        batch_id=row.batch_id,
                        auto_count=0,
                        manual_count=0,
                        lang=lang,
                    ),
                )

    await session.commit()


# ---------------------------------------------------------------------------
# Product Listing
# ---------------------------------------------------------------------------


@router.message(F.text.startswith("/shop_products"))
async def cmd_shop_products(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        return

    shop = await _get_user_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    shop_repo = ShopRepository(session)
    products, total = await shop_repo.get_shop_products_paginated(shop.id, offset=0, limit=10)

    if not products:
        await message.answer(t("products_empty", lang=lang))
        return

    total_pages = max(1, (total + 9) // 10)
    text = _format_product_list(products, page=1, total_pages=total_pages, lang=lang)
    await message.answer(
        text, reply_markup=get_product_list_keyboard(page=1, total_pages=total_pages, lang=lang)
    )


@router.callback_query(F.data.startswith("products_page:"))
async def callback_products_page(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data:
        return
    page = int(callback.data.split(":")[1])

    shop = await _get_user_shop(user, session)
    if not shop:
        return

    shop_repo = ShopRepository(session)
    offset = (page - 1) * 10
    products, total = await shop_repo.get_shop_products_paginated(shop.id, offset=offset, limit=10)

    total_pages = max(1, (total + 9) // 10)
    text = _format_product_list(products, page=page, total_pages=total_pages, lang=lang)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=get_product_list_keyboard(page=page, total_pages=total_pages, lang=lang),
        )


def _format_product_list(
    products: object,
    page: int,
    total_pages: int,
    lang: str,
) -> str:
    """Format product list as text."""
    from collections.abc import Sequence as SeqType

    from app.db.models.shop import ShopProduct as SP

    lines = [t("products_list_title", lang=lang, page=page, total_pages=total_pages), ""]
    if isinstance(products, SeqType):
        for p in products:
            if isinstance(p, SP):
                staleness_badge = {
                    "fresh": "🟢",
                    "aging": "🟡",
                    "stale": "🔴",
                }.get(p.staleness_state, "⚪")
                unit_str = p.pack_unit_code or "dona"
                lines.append(
                    f"{staleness_badge} <b>{p.raw_name}</b>\n"
                    f"   💰 {p.price_per_pack:,.0f} so'm / {p.pack_size:g} {unit_str}\n"
                    f"   📦 {p.stock_status}"
                )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Delivery Rule Editor
# ---------------------------------------------------------------------------


@router.message(F.text.startswith("/delivery_rules"))
async def cmd_delivery_rules(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        return

    shop = await _get_user_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    shop_repo = ShopRepository(session)
    rules = await shop_repo.get_shop_delivery_rules(shop.id)

    text = t("delivery_rules_title", lang=lang) + "\n\n"
    if rules:
        for r in rules:
            district_name = r.district.name_uz if r.district else "Barcha tumanlar"
            free_info = f", bepul {r.free_above:,.0f}+ dan" if r.free_above else ""
            min_info = f", min {r.min_order:,.0f}" if r.min_order > 0 else ""
            text += (
                f"📍 <b>{district_name}</b>: {r.fee:,.0f} so'm{free_info}{min_info} "
                f"({r.eta_hours}h)\n"
            )
    else:
        text += "Hali sozlamalar mavjud emas.\n"

    await message.answer(text)


# Delivery rule update regex:
# "dostavka Chilonzor 30000 free:500000 min:100000"
DELIVERY_RULE_REGEX = re.compile(
    r"^(?:dostavka|доставка)\s+(.+?)\s+(\d+)" r"(?:\s+free[:\s](\d+))?" r"(?:\s+min[:\s](\d+))?$",
    re.IGNORECASE,
)


@router.message(ShopOwnerStates.editing_delivery_rule)
@router.message(lambda msg: bool(msg.text and DELIVERY_RULE_REGEX.match(msg.text.strip())))
async def handle_delivery_rule_update(
    message: Message,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if user.role not in ("shop_owner", "admin"):
        return
    if not message.text:
        return

    match = DELIVERY_RULE_REGEX.match(message.text.strip())
    if not match:
        return

    district_name, fee_str, free_above_str, min_order_str = match.groups()
    fee = Decimal(fee_str)
    free_above = Decimal(free_above_str) if free_above_str else None
    min_order = Decimal(min_order_str) if min_order_str else Decimal("0")

    shop = await _get_user_shop(user, session)
    if not shop:
        await message.answer(t("no_shop_found", lang=lang))
        return

    # Find district by name
    shop_repo = ShopRepository(session)
    districts = await shop_repo.list_districts()
    target_district = None
    district_lower = district_name.lower().strip()
    for d in districts:
        if district_lower in d.name_uz.lower() or district_lower in d.name_ru.lower():
            target_district = d
            break

    await shop_repo.upsert_delivery_rule(
        shop_id=shop.id,
        district_id=target_district.id if target_district else None,
        fee=fee,
        free_above=free_above,
        min_order=min_order,
    )
    await session.commit()

    dist_display = target_district.name_uz if target_district else district_name
    await message.answer(t("delivery_rule_updated", lang=lang, district=dist_display))
