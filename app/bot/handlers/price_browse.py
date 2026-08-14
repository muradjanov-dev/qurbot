"""Category browser for the "Mahsulot narxi" menu button.

Read-only price lookup: category -> subcategory -> cheapest live offer per
product. Deliberately separate from the basket flow -- browsing prices does
not create or touch a basket.
"""

from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import get_price_category_keyboard
from app.core.i18n import t
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository

router = Router(name="price_browse")

_MAX_PRODUCTS = 15


@router.message(F.text.in_(["🔍 Mahsulot narxi", "🔍 Маҳсулот нархи", "🔍 Цены на товары"]))
async def menu_price_check(message: Message, session: AsyncSession, lang: str) -> None:
    catalog_repo = CatalogRepository(session)
    roots = await catalog_repo.list_root_categories()
    await message.answer(
        t("price_browse_choose_category", lang=lang),
        reply_markup=get_price_category_keyboard(roots, lang=lang),
    )


@router.callback_query(F.data.startswith("price_cat:"))
async def callback_price_category(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data:
        return
    category_id = int(callback.data.split(":")[1])

    catalog_repo = CatalogRepository(session)
    category = await catalog_repo.get_category(category_id)
    if category is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    children = await catalog_repo.list_child_categories(category_id)
    if children:
        await callback.message.edit_text(
            t("price_browse_choose_category", lang=lang),
            reply_markup=get_price_category_keyboard(children, lang=lang, parent_id=category_id),
        )
        await callback.answer()
        return

    # Leaf category -- show cheapest live offer per product.
    subtree_ids = await catalog_repo.get_category_subtree_ids(category_id)
    products = await catalog_repo.search_canonical_products(
        "", limit=_MAX_PRODUCTS, category_ids=subtree_ids
    )
    if not products:
        await callback.message.edit_text(t("price_browse_empty", lang=lang))
        await callback.answer()
        return

    shop_repo = ShopRepository(session)
    offers = await shop_repo.get_active_offers_for_canonicals([p.id for p in products])
    # Offers arrive ordered by (canonical_id, price_per_base_unit), so the
    # first one seen per product is its cheapest.
    cheapest: dict[int, Decimal] = {}
    for offer in offers:
        if offer.canonical_id is not None and offer.canonical_id not in cheapest:
            cheapest[offer.canonical_id] = offer.price_per_pack

    category_name = category.name_ru if lang == "ru" else category.name_uz
    lines = [t("price_browse_header", lang=lang, category=category_name)]
    for product in products:
        price = cheapest.get(product.id)
        if price is None:
            continue
        lines.append(f"• {product.name_uz} — <b>{price:,.0f} so'm</b>")

    if len(lines) == 1:
        await callback.message.edit_text(t("price_browse_empty", lang=lang))
        await callback.answer()
        return

    lines.append(t("price_browse_hint", lang=lang))
    await callback.message.edit_text("\n".join(lines))
    await callback.answer()


@router.callback_query(F.data == "price_cat_root")
async def callback_price_category_root(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    catalog_repo = CatalogRepository(session)
    roots = await catalog_repo.list_root_categories()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            t("price_browse_choose_category", lang=lang),
            reply_markup=get_price_category_keyboard(roots, lang=lang),
        )
    await callback.answer()
