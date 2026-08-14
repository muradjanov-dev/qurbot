"""Keyboards for the shop product upload wizard."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.i18n import t
from app.db.models.catalog import Category, Unit

# Units offered as one-tap answers. Ordered by how often construction materials
# are actually sold that way, so the common case is the first button.
COMMON_PACK_UNITS: tuple[str, ...] = ("qop", "dona", "kg", "m2", "m3", "litr", "metr", "quti")


def get_category_keyboard(
    categories: Sequence[Category],
    lang: str = "uz_latn",
    *,
    parent_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        label = cat.name_ru if lang == "ru" else cat.name_uz
        icon = f"{cat.icon} " if cat.icon else ""
        builder.button(text=f"{icon}{label}", callback_data=f"lst_cat:{cat.id}")
    builder.adjust(2)

    if parent_id is not None:
        builder.row(
            InlineKeyboardButton(text=t("btn_back", lang=lang), callback_data="lst_cat_root")
        )
    builder.row(InlineKeyboardButton(text=t("btn_cancel", lang=lang), callback_data="lst_cancel"))
    return builder.as_markup()


def get_unit_keyboard(
    units: Sequence[Unit],
    lang: str = "uz_latn",
    suggested: str | None = None,
) -> InlineKeyboardMarkup:
    """Unit picker, with the matched product's own base unit promoted first."""
    by_code = {u.code: u for u in units}
    ordered: list[str] = []
    if suggested and suggested in by_code:
        ordered.append(suggested)
    ordered.extend(c for c in COMMON_PACK_UNITS if c in by_code and c not in ordered)
    ordered.extend(c for c in by_code if c not in ordered)

    builder = InlineKeyboardBuilder()
    for code in ordered:
        unit = by_code[code]
        label = unit.name_ru if lang == "ru" else unit.name_uz
        mark = "⭐ " if code == suggested else ""
        builder.button(text=f"{mark}{label}", callback_data=f"lst_unit:{code}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text=t("btn_cancel", lang=lang), callback_data="lst_cancel"))
    return builder.as_markup()


def get_skip_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_skip", lang=lang), callback_data="lst_skip")
    builder.button(text=t("btn_cancel", lang=lang), callback_data="lst_cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_photo_step_keyboard(
    lang: str = "uz_latn", *, has_photos: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_photos:
        builder.button(
            text=t("btn_listing_photos_done", lang=lang), callback_data="lst_photos_done"
        )
    else:
        builder.button(text=t("btn_skip", lang=lang), callback_data="lst_skip")
    builder.button(text=t("btn_cancel", lang=lang), callback_data="lst_cancel")
    builder.adjust(1, 1)
    return builder.as_markup()


def get_review_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_listing_save", lang=lang), callback_data="lst_save")
    builder.button(text=t("btn_listing_edit", lang=lang), callback_data="lst_restart")
    builder.button(text=t("btn_cancel", lang=lang), callback_data="lst_cancel")
    builder.adjust(1, 2)
    return builder.as_markup()


def get_resume_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_listing_resume", lang=lang), callback_data="lst_resume")
    builder.button(text=t("btn_listing_start_new", lang=lang), callback_data="lst_discard_new")
    builder.adjust(1)
    return builder.as_markup()


def get_saved_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_listing_another", lang=lang), callback_data="lst_new")
    builder.button(text=t("btn_back", lang=lang), callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()
