"""Keyboards for the shop product upload wizard."""

from collections.abc import Sequence
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.i18n import t

# Units offered as one-tap answers. Ordered by how often construction materials
# are actually sold that way, so the common case is the first button.
COMMON_PACK_UNITS: tuple[str, ...] = ("qop", "dona", "kg", "m2", "m3", "litr", "metr", "quti")


def get_saved_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_listing_another", lang=lang), callback_data="lst_new")
    builder.button(text=t("btn_back", lang=lang), callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def get_pack_keyboard(
    suggestions: Sequence[tuple[Decimal, str]], lang: str = "uz_latn"
) -> InlineKeyboardMarkup:
    """One-tap pack choices, drawn from how the product is actually sold."""
    builder = InlineKeyboardBuilder()
    for size, unit in suggestions:
        label = f"{format(size.normalize(), 'f')} {unit}"
        builder.button(text=label, callback_data=f"lst_pack:{size}:{unit}")
    builder.button(text=t("btn_pack_other", lang=lang), callback_data="lst_pack_other")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text=t("btn_cancel", lang=lang), callback_data="lst_cancel"))
    return builder.as_markup()


def get_price_confirm_keyboard(lang: str = "uz_latn") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_price_correct", lang=lang), callback_data="lst_price_ok")
    builder.button(text=t("btn_price_fix", lang=lang), callback_data="lst_price_fix")
    builder.adjust(2)
    return builder.as_markup()
