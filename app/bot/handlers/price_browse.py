"""Product catalogue browser for the "Mahsulotlar va narxlar" menu button.

Category -> product list -> product card with the cheapest live offer and,
when a shop owner has uploaded one, a photo. A product card can also add
a chosen quantity to the customer's basket.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import (
    esc,
    format_catalog_price,
    format_qty,
    format_uzs,
    localized_name,
)
from app.bot.handlers.customer import _format_parse_table, _load_durable_cart, _persist_bot_cart
from app.bot.keyboards.inline import (
    get_all_products_keyboard,
    get_basket_actions_keyboard,
    get_price_category_keyboard,
    get_product_detail_keyboard,
    get_product_picker_keyboard,
)
from app.bot.states import BasketStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.parsing.parser import is_qty_orderable

logger = logging.getLogger(__name__)

router = Router(name="price_browse")

_CATEGORY_PAGE_SIZE = 30


def _full_product_list(
    products: list[tuple[CanonicalProduct, str]], lang: str, *, start: int = 1
) -> str:
    """The message carries full names and prices; buttons carry short numbered choices."""
    rows = []
    for number, (product, price) in enumerate(products, start=start):
        name = localized_name(
            product.name_uz,
            product.name_ru,
            lang,
            name_uz_cyrl=getattr(product, "name_uz_cyrl", None),
        )
        rows.append(f"{number}. {esc(name)} — {esc(price)}")
    return "\n".join(rows)


async def _replace_catalog_screen(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    """Replace a catalogue screen even when the current message is media.

    Telegram cannot turn a photo/caption message into a text message with
    ``edit_text``. Product cards with photos therefore need to be removed and
    followed by a fresh text screen when the customer navigates back.
    """
    if message.text is not None:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except TelegramAPIError as exc:
            if "message is not modified" in str(exc).lower():
                return
            logger.warning("catalog_screen_edit_failed", exc_info=True)

    try:
        await message.delete()
    except TelegramAPIError:
        # An old message may already be gone or no longer deletable. Navigation
        # must still work, so send the destination screen regardless.
        logger.warning("catalog_screen_delete_failed", exc_info=True)
    await message.answer(text, reply_markup=reply_markup)


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
    parts = callback.data.split(":")
    category_id = int(parts[1])
    page = max(0, int(parts[2])) if len(parts) > 2 else 0

    catalog_repo = CatalogRepository(session)
    category = await catalog_repo.get_category(category_id)
    if category is None:
        await callback.answer()
        return

    children = await catalog_repo.list_child_categories(category_id)
    if children:
        await _replace_catalog_screen(
            callback.message,
            t("price_browse_choose_category", lang=lang),
            get_price_category_keyboard(children, lang=lang, parent_id=category_id),
        )
        await callback.answer()
        return

    subtree_ids = await catalog_repo.get_category_subtree_ids(category_id)
    rows, total = await catalog_repo.list_catalog_page(
        offset=page * _CATEGORY_PAGE_SIZE,
        limit=_CATEGORY_PAGE_SIZE,
        category_ids=subtree_ids,
    )
    pages = max(1, (total + _CATEGORY_PAGE_SIZE - 1) // _CATEGORY_PAGE_SIZE)
    if page >= pages:
        page = pages - 1
        rows, _ = await catalog_repo.list_catalog_page(
            offset=page * _CATEGORY_PAGE_SIZE,
            limit=_CATEGORY_PAGE_SIZE,
            category_ids=subtree_ids,
        )
    if not rows:
        await _replace_catalog_screen(
            callback.message,
            t("price_browse_empty", lang=lang, phone=settings.support_phone_text),
            get_price_category_keyboard([], lang=lang, parent_id=category_id),
        )
        await callback.answer()
        return

    products = [product for product, _ in rows]
    cheapest = await _cheapest_by_canonical(session, [product.id for product in products])
    # Every product is listed, priced from the cheapest live offer when a shop
    # carries it and from the supplier's list price otherwise. Listing only
    # products with a live offer meant the whole catalogue read as empty until
    # the first shop uploaded, which is not what a customer should be told.
    listed = [
        (
            product,
            format_catalog_price(cheapest.get(product.id), product.reference_price, lang=lang),
        )
        for product in products
    ]

    category_name = localized_name(category.name_uz, category.name_ru, lang)
    await _replace_catalog_screen(
        callback.message,
        t("price_browse_header", lang=lang, category=category_name)
        + "\n\n"
        + _full_product_list(listed, lang, start=page * _CATEGORY_PAGE_SIZE + 1),
        get_product_picker_keyboard(
            listed,
            lang=lang,
            category_id=category_id,
            page=page,
            pages=pages,
            page_size=_CATEGORY_PAGE_SIZE,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("all_prod:"))
async def callback_all_products(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    """The whole catalogue, a page at a time, for customers.

    Browsing by category assumes the customer already knows which category
    their product sits in. Paging through everything is the shortest path when
    they just want to see what is carried and what it costs.
    """
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    try:
        page = max(0, int(callback.data.split(":")[1]))
    except ValueError:
        page = 0

    page_size = settings.customer_products_page_size
    catalog_repo = CatalogRepository(session)
    rows, total = await catalog_repo.list_catalog_page(offset=page * page_size, limit=page_size)
    if not rows:
        await _replace_catalog_screen(
            callback.message,
            t("price_browse_empty", lang=lang, phone=settings.support_phone_text),
            get_price_category_keyboard([], lang=lang),
        )
        await callback.answer()
        return

    pages = max(1, (total + page_size - 1) // page_size)
    listed = [
        (product, format_catalog_price(live_price, product.reference_price, lang=lang))
        for product, live_price in rows
    ]

    await _replace_catalog_screen(
        callback.message,
        f"{t('all_products_header', lang=lang, count=total)}\n"
        f"{t('price_reference_hint', lang=lang)}\n\n"
        + _full_product_list(listed, lang, start=page * page_size + 1),
        get_all_products_keyboard(listed, page=page, pages=pages, lang=lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("price_prod:"))
async def callback_product_detail(
    callback: CallbackQuery,
    session: AsyncSession,
    lang: str,
) -> None:
    """Show one product: its price range and a photo.

    Deliberately says nothing about which shops carry it or how many. The
    customer is buying from us, so the supply side is not their concern.
    """
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    parts = callback.data.split(":")
    canonical_id = int(parts[1])
    category_page = int(parts[2]) if len(parts) > 2 else None

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
            name=esc(product.name_uz),
            brand=esc(product.brand or "—"),
            min_price=format_uzs(min(prices)),
            max_price=format_uzs(max(prices)),
            unit=product.base_unit_code,
        )
    else:
        body = t(
            "product_card_no_offers",
            lang=lang,
            name=esc(product.name_uz),
            phone=settings.support_phone_text,
        )

    photo = await shop_repo.get_photo_for_canonical(canonical_id)
    keyboard = get_product_detail_keyboard(
        product.category_id, lang=lang, canonical_id=canonical_id, category_page=category_page
    )

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
        await _replace_catalog_screen(
            callback.message,
            t("price_browse_choose_category", lang=lang),
            get_price_category_keyboard(roots, lang=lang),
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


PENDING_PRODUCT_KEY = "pending_canonical_id"


@router.callback_query(F.data.startswith("price_add:"))
async def callback_add_to_basket(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
) -> None:
    """Start adding a browsed product to the basket by asking for a quantity."""
    if not callback.data or not isinstance(callback.message, Message):
        await callback.answer()
        return
    canonical_id = int(callback.data.split(":")[1])

    product = await CatalogRepository(session).get(canonical_id)
    if product is None:
        await callback.answer()
        return

    await state.update_data({PENDING_PRODUCT_KEY: canonical_id})
    await state.set_state(BasketStates.entering_qty_for_product)
    await callback.message.answer(
        t(
            "price_ask_qty",
            lang=lang,
            name=esc(product.name_uz),
            unit=esc(product.base_unit_code),
        )
    )
    await callback.answer()


@router.message(BasketStates.entering_qty_for_product, F.text)
async def handle_product_qty(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
) -> None:
    """Append the browsed product to the basket, then show the basket itself.

    Reuses the same basket_lines shape the text parser produces, so the line
    flows through the existing review table and quote path untouched.
    """
    if not message.text:
        return

    raw = message.text.strip().replace(",", ".")
    try:
        qty = Decimal(raw)
    except InvalidOperation:
        await message.answer(t("price_qty_not_a_number", lang=lang))
        return

    if not is_qty_orderable(qty, max_qty=Decimal(settings.basket_max_qty)):
        await message.answer(t("qty_out_of_range", lang=lang))
        return

    existing = await _load_durable_cart(state, session)
    data = await state.get_data()
    canonical_id = data.get(PENDING_PRODUCT_KEY)
    if canonical_id is None:
        await state.set_state(BasketStates.viewing_quotes)
        return

    product = await CatalogRepository(session).get(int(canonical_id))
    if product is None:
        await state.set_state(BasketStates.viewing_quotes)
        return

    lines = [dict(item) for item in existing]
    matching = next((item for item in lines if item.get("canonical_id") == product.id), None)
    if matching is not None:
        qty += Decimal(str(matching["qty"]))
        if not is_qty_orderable(qty, max_qty=Decimal(settings.basket_max_qty)):
            await message.answer(t("qty_out_of_range", lang=lang))
            return
        matching["qty"] = str(qty)
        matching["raw_text"] = f"{format_qty(qty)} {product.base_unit_code} {product.name_uz}"
    else:
        line_no = max((item["line_no"] for item in lines), default=0) + 1
        lines.append(
            {
                "line_no": line_no,
                "raw_text": f"{format_qty(qty)} {product.base_unit_code} {product.name_uz}",
                "parsed_name": product.name_uz,
                "qty": str(qty),
                "unit_code": product.base_unit_code,
                "status": "auto_accept",
                "method": "catalog_pick",
                "confidence": 1.0,
                "canonical_id": product.id,
                "canonical_name": product.name_uz,
                "candidates": [],
            }
        )

    if not await _persist_bot_cart(state, session, lines):
        await message.answer(t("web_error_generic", lang=lang))
        return

    await message.answer(
        t(
            "price_added_to_basket",
            lang=lang,
            name=esc(product.name_uz),
            qty=format_qty(qty),
            unit=esc(product.base_unit_code),
        )
    )

    table = await message.answer(
        _format_parse_table(lines, lang=lang),
        reply_markup=get_basket_actions_keyboard(
            lang=lang, line_numbers=[item["line_no"] for item in lines]
        ),
    )
    await state.set_state(BasketStates.viewing_quotes)
    await state.update_data(
        basket_lines=lines,
        pending_canonical_id=None,
        table_chat_id=table.chat.id,
        table_message_id=table.message_id,
    )
