"""Product catalogue browser for the "Mahsulotlar va narxlar" menu button.

Read-only: category -> product list -> product card with the cheapest live
offer and, when a shop owner has uploaded one, a photo. Browsing never
creates or touches a basket.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import (
    get_price_category_keyboard,
    get_product_detail_keyboard,
    get_product_picker_keyboard,
)
from app.core.i18n import t
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository

logger = logging.getLogger(__name__)

router = Router(name="price_browse")

_MAX_PRODUCTS = 30


@router.message(
    F.text.in_(
        [
            "🛒 Mahsulotlar va narxlar",
            "🛒 Маҳсулотлар ва нархлар",
            "🛒 Товары и цены",
        ]
    )
)
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
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    category_id = int(callback.data.split(":")[1])

    catalog_repo = CatalogRepository(session)
    category = await catalog_repo.get_category(category_id)
    if category is None:
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

    subtree_ids = await catalog_repo.get_category_subtree_ids(category_id)
    products = await catalog_repo.search_canonical_products(
        "", limit=_MAX_PRODUCTS, category_ids=subtree_ids
    )
    if not products:
        await callback.message.edit_text(t("price_browse_empty", lang=lang))
        await callback.answer()
        return

    cheapest = await _cheapest_by_canonical(session, [p.id for p in products])
    # Only products with a live offer are listed -- a row with no price is
    # nothing the customer can act on.
    listed = [(p, price) for p in products if (price := cheapest.get(p.id)) is not None]
    if not listed:
        await callback.message.edit_text(t("price_browse_empty", lang=lang))
        await callback.answer()
        return

    category_name = category.name_ru if lang == "ru" else category.name_uz
    await callback.message.edit_text(
        t("price_browse_header", lang=lang, category=category_name),
        reply_markup=get_product_picker_keyboard(listed, lang=lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("price_prod:"))
async def callback_product_detail(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    """Show one product: cheapest price, how many shops carry it, and a photo."""
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    canonical_id = int(callback.data.split(":")[1])

    catalog_repo = CatalogRepository(session)
    product = await catalog_repo.get(canonical_id)
    if product is None:
        await callback.answer()
        return

    shop_repo = ShopRepository(session)
    offers = await shop_repo.get_active_offers_for_canonicals([canonical_id])
    if offers:
        prices = [o.price_per_pack for o in offers]
        body = t(
            "product_card",
            lang=lang,
            name=product.name_uz,
            brand=product.brand or "—",
            min_price=f"{min(prices):,.0f}",
            max_price=f"{max(prices):,.0f}",
            shops=len(offers),
            unit=product.base_unit_code,
        )
    else:
        body = t("product_card_no_offers", lang=lang, name=product.name_uz)

    photo = await shop_repo.get_photo_for_canonical(canonical_id)
    keyboard = get_product_detail_keyboard(product.category_id, lang=lang)

    if photo is not None:
        file_id, blob = photo
        try:
            await callback.message.answer_photo(file_id, caption=body, reply_markup=keyboard)
            await callback.answer()
            return
        except TelegramAPIError:
            # A file_id does not survive a bot-token rotation; the stored bytes do.
            logger.warning("product_photo_file_id_failed canonical=%s", canonical_id)
            if blob:
                await callback.message.answer_photo(
                    BufferedInputFile(blob, filename=f"product_{canonical_id}.jpg"),
                    caption=body,
                    reply_markup=keyboard,
                )
                await callback.answer()
                return

    await callback.message.answer(body, reply_markup=keyboard)
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


async def _cheapest_by_canonical(
    session: AsyncSession, canonical_ids: list[int]
) -> dict[int, Decimal]:
    """Cheapest live pack price per product.

    get_active_offers_for_canonicals orders by (canonical_id, price_per_base_unit),
    so the first offer seen for a product is its cheapest.
    """
    shop_repo = ShopRepository(session)
    offers = await shop_repo.get_active_offers_for_canonicals(canonical_ids)
    cheapest: dict[int, Decimal] = {}
    for offer in offers:
        if offer.canonical_id is not None and offer.canonical_id not in cheapest:
            cheapest[offer.canonical_id] = offer.price_per_pack
    return cheapest
