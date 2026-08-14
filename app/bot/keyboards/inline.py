from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.i18n import t
from app.db.models.catalog import Category
from app.db.models.shop import District
from app.domain.matching.models import CandidateMatch


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

    if parent_id is not None:
        builder.row(
            InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="price_cat_root")
        )
    return builder.as_markup()


def get_language_keyboard() -> InlineKeyboardMarkup:
    """Build language selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇿 O'zbekcha", callback_data="set_lang:uz_latn")
    builder.button(text="🇺🇿 Ўзбекча", callback_data="set_lang:uz_cyrl")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang:ru")
    builder.adjust(1)
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


def get_basket_actions_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    """Build action buttons for parsed basket view."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_calculate_quotes", lang=lang), callback_data="calculate_quotes")
    builder.button(text=t("btn_edit_basket", lang=lang), callback_data="edit_basket")
    builder.button(text=t("btn_add_item", lang=lang), callback_data="add_item")
    builder.button(text=t("btn_clear_basket", lang=lang), callback_data="clear_basket")
    builder.button(text=t("btn_back", lang=lang), callback_data="back_to_menu")
    builder.adjust(1, 3, 1)
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
) -> InlineKeyboardMarkup:
    """Build carousel navigation keyboard for quotes: [◀] 1/4 [▶] + actions."""
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

    # Action row 1: Select quote
    builder.row(
        InlineKeyboardButton(
            text=t("btn_select_quote", lang=lang),
            callback_data=f"select_quote:{current_index}",
        )
    )

    # Action row 2: PDF & Recalculate
    builder.row(
        InlineKeyboardButton(
            text=t("btn_get_pdf", lang=lang),
            callback_data=f"pdf_quote:{current_index}",
        ),
        InlineKeyboardButton(
            text=t("btn_recalculate", lang=lang),
            callback_data="calculate_quotes",
        ),
    )
    return builder.as_markup()


def get_shop_order_decision_keyboard(order_part_id: int) -> InlineKeyboardMarkup:
    """Build shop owner accept/reject buttons for incoming order part."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Qabul qilish", callback_data=f"shop_order:accept:{order_part_id}")
    builder.button(text="❌ Rad etish", callback_data=f"shop_order:reject:{order_part_id}")
    builder.adjust(2)
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
) -> InlineKeyboardMarkup:
    """Build paginated product list navigation."""
    builder = InlineKeyboardBuilder()
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
