from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct, Category
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import UserAddress
from app.domain.matching.models import CandidateMatch


def get_shop_picker_keyboard(
    shops: Sequence["Shop"], lang: str = "uz_latn"
) -> InlineKeyboardMarkup:
    """Branch picker for owners who run more than one shop."""
    builder = InlineKeyboardBuilder()
    for shop in shops:
        district = shop.district.name_ru if lang == "ru" else shop.district.name_uz
        builder.button(text=f"{shop.name} — {district}", callback_data=f"shp:pick:{shop.id}")
    builder.adjust(1)
    return builder.as_markup()


def get_upload_template_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    """Offered alongside the upload prompt.

    "Send your Excel here" is not enough on its own: nothing on that screen
    said which columns the importer reads, so an owner had to guess and find
    out only after a failed import.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("shp_btn_template", lang=lang), callback_data="shp:template")
    builder.adjust(1)
    return builder.as_markup()


def get_shop_panel_inline_keyboard(
    lang: str = "uz_latn", show_switch: bool = False
) -> InlineKeyboardMarkup:
    """Actions for the shop-owner panel, as buttons instead of typed commands."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("shp_btn_quick_price", lang=lang), callback_data="shp:quick_price")
    builder.button(text=t("shp_btn_products", lang=lang), callback_data="shp:products")
    builder.button(text=t("shp_btn_add_product", lang=lang), callback_data="shp:add_product")
    builder.button(text=t("shp_btn_upload", lang=lang), callback_data="shp:upload")
    builder.button(text=t("shp_btn_delivery", lang=lang), callback_data="shp:delivery")
    builder.button(text=t("shp_btn_orders", lang=lang), callback_data="shp:orders")
    builder.adjust(2, 2, 2)
    if show_switch:
        builder.row(
            InlineKeyboardButton(
                text=t("shp_btn_switch_shop", lang=lang), callback_data="shp:switch"
            )
        )
    return builder.as_markup()


def get_admin_panel_keyboard(
    lang: str = "uz_latn", is_super_admin: bool = False
) -> InlineKeyboardMarkup:
    """Build the in-bot admin panel menu.

    The admin-management entry is only rendered for super admins, so a
    promoted admin cannot hand out further admin rights.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=t("adm_btn_stats", lang=lang), callback_data="adm:stats")
    builder.button(text=t("adm_btn_shops", lang=lang), callback_data="adm:shops")
    builder.button(text=t("adm_btn_products", lang=lang), callback_data="adm:products")
    builder.button(text=t("adm_btn_users", lang=lang), callback_data="adm:users")
    builder.button(text=t("adm_btn_unmatched", lang=lang), callback_data="adm:unmatched")
    builder.button(text=t("adm_btn_add_shop", lang=lang), callback_data="adm:add_shop")
    builder.adjust(2, 2, 2)
    if is_super_admin:
        builder.row(
            InlineKeyboardButton(text=t("adm_btn_admins", lang=lang), callback_data="adm:admins")
        )
    return builder.as_markup()


def get_admin_back_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_back", lang=lang), callback_data="adm:home")
    return builder.as_markup()


def get_admin_admins_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("adm_btn_add_admin", lang=lang), callback_data="adm:add_admin")
    builder.button(text=t("btn_back", lang=lang), callback_data="adm:home")
    builder.adjust(1)
    return builder.as_markup()


def get_price_category_keyboard(
    categories: Sequence[Category],
    lang: str = "uz_latn",
    parent_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Build the category picker for the read-only price browser."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        label = cat.name_ru if lang == "ru" else cat.name_uz
        icon = f"{cat.icon} " if cat.icon else ""
        builder.button(text=f"{icon}{label}", callback_data=f"price_cat:{cat.id}")
    builder.adjust(2)

    if parent_id is None:
        # Browsing by category assumes the customer knows which category their
        # product is in. For a catalogue this size, letting them page through
        # all of it is faster than guessing.
        builder.row(
            InlineKeyboardButton(text=t("btn_all_products", lang=lang), callback_data="all_prod:0")
        )
    else:
        builder.row(
            InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="price_cat_root")
        )
    return builder.as_markup()


def get_product_picker_keyboard(
    products: Sequence[tuple["CanonicalProduct", str]],
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """Product list where each row is tappable and shows its price.

    The price arrives already rendered because what to show depends on where
    it came from -- a live offer, a supplier's list, or nothing at all.
    """
    builder = InlineKeyboardBuilder()
    for product, price_text in products:
        builder.button(
            text=f"{product.name_uz} — {price_text}",
            callback_data=f"price_prod:{product.id}",
        )
    builder.button(text=t("btn_back", lang=lang), callback_data="price_cat_root")
    builder.adjust(1)
    return builder.as_markup()


def get_all_products_keyboard(
    products: Sequence[tuple["CanonicalProduct", str]],
    page: int,
    pages: int,
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """One page of the whole catalogue, for customers rather than operators."""
    builder = InlineKeyboardBuilder()
    for product, price_text in products:
        builder.button(
            text=f"{product.name_uz} — {price_text}",
            callback_data=f"price_prod:{product.id}",
        )
    builder.adjust(1)

    if pages > 1:
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=f"all_prod:{(page - 1) % pages}"),
            InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"all_prod:{(page + 1) % pages}"),
        )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="price_cat_root"))
    return builder.as_markup()


def get_product_detail_keyboard(
    category_id: int | None,
    lang: str = "uz_latn",
    canonical_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if canonical_id is not None:
        builder.button(
            text=t("btn_add_to_basket", lang=lang),
            callback_data=f"price_add:{canonical_id}",
        )
    if category_id is not None:
        builder.button(text=t("btn_back", lang=lang), callback_data=f"price_cat:{category_id}")
    else:
        builder.button(text=t("btn_back", lang=lang), callback_data="price_cat_root")
    builder.adjust(1)
    return builder.as_markup()


def get_language_keyboard(
    change_only: bool = False,
    show_back: bool = False,
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """Build language selection keyboard.

    `change_only` switches the callback prefix so picking a language from
    Settings only changes the language, instead of dropping the user back
    into the district/phone onboarding steps they already completed.
    """
    prefix = "chg_lang" if change_only else "set_lang"
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇿 O'zbekcha (lotin)", callback_data=f"{prefix}:uz_latn")
    builder.button(text="🇺🇿 Ўзбекча (кирилл)", callback_data=f"{prefix}:uz_cyrl")
    builder.button(text="🇷🇺 Русский", callback_data=f"{prefix}:ru")
    builder.adjust(1)
    if show_back:
        builder.row(
            InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="settings:back")
        )
    return builder.as_markup()


def get_settings_inline_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    """Build settings menu keyboard with language change and re-registration options."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_change_language", lang=lang), callback_data="settings:language")
    builder.button(text=t("btn_reregister", lang=lang), callback_data="settings:reregister")
    builder.adjust(1)
    return builder.as_markup()


def get_reregister_confirm_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    """Build confirmation buttons for re-registering from scratch."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_confirm_reregister", lang=lang), callback_data="reregister:confirm")
    builder.button(text=t("btn_cancel_reregister", lang=lang), callback_data="reregister:cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_district_keyboard(
    districts: Sequence[District], lang: str = "uz_latn"
) -> InlineKeyboardMarkup:
    """Build district selection keyboard in 2 columns."""
    builder = InlineKeyboardBuilder()
    for d in districts:
        name = d.name_ru if lang == "ru" else d.name_uz
        builder.button(text=name, callback_data=f"set_district:{d.id}")
    builder.adjust(2)
    return builder.as_markup()


# Beyond this many lines the per-line rows push the order button off the
# screen, and a customer scrolling past their own basket to reach it is worse
# off than one who retypes a long list.
MAX_PER_LINE_ROWS = 8


def get_basket_actions_keyboard(
    lang: str = "uz_latn",
    line_numbers: Sequence[int] | None = None,
) -> InlineKeyboardMarkup:
    """Build action buttons for parsed basket view.

    Order follows the order of the work: correct the list first, then order it.
    Ordering sat at the top, above the buttons for fixing what it would be
    ordering -- so the last thing the customer reads is now the thing they came
    to do.

    `line_numbers` adds a row per product: change this one, remove this one.
    Without them the only tools were "rewrite the whole list" and "delete
    everything", so fixing the third of three items meant retyping all three.
    """
    builder = InlineKeyboardBuilder()

    for line_no in list(line_numbers or [])[:MAX_PER_LINE_ROWS]:
        builder.row(
            InlineKeyboardButton(
                text=t("btn_line_edit", lang=lang, line=line_no),
                callback_data=f"line_edit:{line_no}",
            ),
            InlineKeyboardButton(
                text=t("btn_line_delete", lang=lang, line=line_no),
                callback_data=f"line_del:{line_no}",
            ),
        )

    builder.row(
        InlineKeyboardButton(text=t("btn_add_item", lang=lang), callback_data="add_item"),
        InlineKeyboardButton(text=t("btn_clear_basket", lang=lang), callback_data="clear_basket"),
    )
    builder.row(InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="back_to_menu"))
    builder.row(
        InlineKeyboardButton(
            text=t("btn_calculate_quotes", lang=lang), callback_data="calculate_quotes"
        )
    )
    return builder.as_markup()


def get_order_confirm_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    """Build confirm/cancel buttons for the final order review screen."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_confirm_order", lang=lang), callback_data="confirm_order")
    builder.button(text=t("btn_back", lang=lang), callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def get_candidate_picker_keyboard(
    line_no: int,
    candidates: Sequence[CandidateMatch],
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """Build inline candidate picker for ambiguous lines (⚠️)."""
    builder = InlineKeyboardBuilder()
    for cand in candidates[:3]:
        name = cand.name_uz
        builder.button(text=name, callback_data=f"pick_cand:{line_no}:{cand.canonical_id}")
    builder.button(text="✍️ Boshqa (qo'lda kiritish)", callback_data=f"pick_custom:{line_no}")
    builder.adjust(1)
    return builder.as_markup()


def get_quote_carousel_keyboard(
    current_index: int,
    total_variants: int,
    lang: str = "uz_latn",
    *,
    has_photos: bool = False,
    is_orderable: bool = True,
) -> InlineKeyboardMarkup:
    """Build carousel navigation keyboard for quotes: [◀] 1/4 [▶] + actions.

    `is_orderable` is False for a variant that sourced nothing. Its buttons are
    left off rather than shown and rejected: an enabled "confirm" button is a
    promise that pressing it does something.
    """
    builder = InlineKeyboardBuilder()

    # Navigation row
    prev_idx = (current_index - 1) % total_variants
    next_idx = (current_index + 1) % total_variants

    nav_buttons = [
        InlineKeyboardButton(text="◀️", callback_data=f"nav_quote:{prev_idx}"),
        InlineKeyboardButton(text=f"{current_index + 1}/{total_variants}", callback_data="noop"),
        InlineKeyboardButton(text="▶️", callback_data=f"nav_quote:{next_idx}"),
    ]
    builder.row(*nav_buttons)

    if is_orderable:
        # Action row 1: Select quote
        builder.row(
            InlineKeyboardButton(
                text=t("btn_select_quote", lang=lang),
                callback_data=f"select_quote:{current_index}",
            )
        )

        # Action row 2: PDF & back. Recalculating from here re-ran the same
        # optimisation over the same basket and returned the same numbers,
        # which left no way back to the basket to change anything.
        builder.row(
            InlineKeyboardButton(
                text=t("btn_get_pdf", lang=lang),
                callback_data=f"pdf_quote:{current_index}",
            ),
            InlineKeyboardButton(
                text=t("btn_back_to_basket", lang=lang),
                callback_data="back_to_basket",
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=t("btn_back_to_basket", lang=lang),
                callback_data="back_to_basket",
            )
        )

    # Photos are opt-in rather than inlined: sending them alongside the card
    # would push the totals off screen, and only some products have any.
    if has_photos:
        builder.row(
            InlineKeyboardButton(
                text=t("btn_view_photos", lang=lang),
                callback_data=f"quote_photos:{current_index}",
            )
        )
    return builder.as_markup()


def get_shop_order_decision_keyboard(order_part_id: int) -> InlineKeyboardMarkup:
    """Build shop owner accept/reject buttons for incoming order part."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Qabul qilish", callback_data=f"shop_order:accept:{order_part_id}")
    builder.button(text="❌ Rad etish", callback_data=f"shop_order:reject:{order_part_id}")
    builder.adjust(2)
    return builder.as_markup()


def get_product_edit_keyboard(
    product_id: int, is_active: bool, lang: str = "uz_latn"
) -> InlineKeyboardMarkup:
    """Edit actions for a single shop product."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("prod_btn_edit_price", lang=lang), callback_data=f"prod:price:{product_id}"
    )
    builder.button(
        text=t("prod_btn_edit_stock", lang=lang), callback_data=f"prod:stock:{product_id}"
    )
    if is_active:
        builder.button(
            text=t("prod_btn_deactivate", lang=lang), callback_data=f"prod:off:{product_id}"
        )
    else:
        builder.button(
            text=t("prod_btn_activate", lang=lang), callback_data=f"prod:on:{product_id}"
        )
    builder.button(text=t("btn_back", lang=lang), callback_data="products_page:1")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def get_stock_status_keyboard(product_id: int, lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code in ("in_stock", "low", "on_order", "out"):
        builder.button(
            text=t(f"prod_stock_{code}", lang=lang),
            callback_data=f"prod:setstock:{product_id}:{code}",
        )
    builder.button(text=t("btn_back", lang=lang), callback_data=f"prod:view:{product_id}")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_import_batch_keyboard(
    batch_id: int,
    auto_count: int,
    manual_count: int,
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """Build import batch confirmation/review/cancel buttons."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=t("btn_confirm_all", lang=lang),
        callback_data=f"import_confirm:{batch_id}",
    )
    if manual_count > 0:
        builder.button(
            text=t("btn_review_unmatched", lang=lang),
            callback_data=f"import_review:{batch_id}",
        )
    builder.button(
        text=t("btn_cancel_import", lang=lang),
        callback_data=f"import_cancel:{batch_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


def get_import_preview_keyboard(
    batch_id: int,
    page: int,
    total_pages: int,
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """Page through a staged price list, then confirm or cancel the whole of it.

    Navigation only appears when there is more than one page: a single arrow
    that wraps to the page you are already on is noise on a phone.
    """
    builder = InlineKeyboardBuilder()

    if total_pages > 1:
        prev_page = (page - 2) % total_pages + 1
        next_page = page % total_pages + 1
        builder.row(
            InlineKeyboardButton(
                text=t("btn_import_prev", lang=lang),
                callback_data=f"imp_page:{batch_id}:{prev_page}",
            ),
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
            InlineKeyboardButton(
                text=t("btn_import_next", lang=lang),
                callback_data=f"imp_page:{batch_id}:{next_page}",
            ),
        )

    builder.row(
        InlineKeyboardButton(
            text=t("btn_confirm_all", lang=lang),
            callback_data=f"import_confirm:{batch_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("btn_cancel_import", lang=lang),
            callback_data=f"import_cancel:{batch_id}",
        )
    )
    return builder.as_markup()


def get_unmatched_row_keyboard(
    row_id: int,
    candidates: list[tuple[int, str, float]],
    lang: str = "uz_latn",
) -> InlineKeyboardMarkup:
    """Build candidate picker for unmatched import row.

    candidates: list of (canonical_id, name, score) tuples.
    """
    builder = InlineKeyboardBuilder()
    for canonical_id, name, score in candidates[:5]:
        label = f"{'✅' if score >= 0.8 else '🔹'} {name} ({score:.0%})"
        builder.button(text=label, callback_data=f"import_resolve:{row_id}:{canonical_id}")
    builder.button(text="⏭ O'tkazib yuborish", callback_data=f"import_skip:{row_id}")
    builder.adjust(1)
    return builder.as_markup()


def get_price_nudge_keyboard() -> InlineKeyboardMarkup:
    """Build the 'Yangilash' button for the daily aging-price nudge (§10 nudge_shops)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Yangilash", callback_data="products_page:1")
    return builder.as_markup()


def get_product_list_keyboard(
    page: int,
    total_pages: int,
    lang: str = "uz_latn",
    products: Sequence["ShopProduct"] | None = None,
) -> InlineKeyboardMarkup:
    """Paginated product list where each row opens that product for editing."""
    builder = InlineKeyboardBuilder()

    for product in products or ():
        builder.row(
            InlineKeyboardButton(
                text=f"{product.raw_name} — {product.price_per_pack:,.0f}",
                callback_data=f"prod:view:{product.id}",
            )
        )

    nav_buttons: list[InlineKeyboardButton] = []

    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"products_page:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="products_noop")
    )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"products_page:{page + 1}")
        )

    builder.row(*nav_buttons)
    return builder.as_markup()


def get_address_confirm_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_address_confirm", lang=lang), callback_data="addr_ok")
    builder.button(text=t("btn_address_edit", lang=lang), callback_data="addr_edit")
    builder.adjust(2)
    return builder.as_markup()


def get_address_picker_keyboard(
    addresses: Sequence["UserAddress"], lang: str = "uz_latn"
) -> InlineKeyboardMarkup:
    """Saved places to deliver to, plus a way to add another.

    The label is trimmed hard: Telegram truncates long button text anyway, and
    a customer recognises their own address from its first few words.
    """
    builder = InlineKeyboardBuilder()
    for addr in addresses:
        text = addr.label or addr.address_text
        if len(text) > 40:
            text = text[:37] + "..."
        mark = "📍 " if addr.is_default else ""
        builder.button(text=f"{mark}{text}", callback_data=f"addr_pick:{addr.id}")
    builder.button(text=t("btn_new_address", lang=lang), callback_data="addr_new")
    builder.adjust(1)
    return builder.as_markup()


def get_admin_products_keyboard(
    page: int, pages: int, lang: str = "uz_latn"
) -> InlineKeyboardMarkup:
    """Paging for the catalogue list, so an admin can reach every product."""
    builder = InlineKeyboardBuilder()
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:products:{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:products:{page + 1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="adm:home"))
    return builder.as_markup()
