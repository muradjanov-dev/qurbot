from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.i18n import t


def get_main_menu_keyboard(
    lang: str = "uz_latn", is_shop_owner: bool = False
) -> ReplyKeyboardMarkup:
    """Build main menu reply keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("menu_send_list", lang=lang))
    builder.button(text=t("menu_my_orders", lang=lang))
    builder.button(text=t("menu_price_check", lang=lang))
    if is_shop_owner:
        builder.button(text=t("menu_shop_portal", lang=lang))
    builder.button(text=t("menu_settings", lang=lang))
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_phone_request_keyboard(lang: str = "uz_latn") -> ReplyKeyboardMarkup:
    """Build phone request keyboard with contact sharing and skip button."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("btn_send_contact", lang=lang), request_contact=True)
    builder.button(text=t("btn_skip", lang=lang))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


def get_cancel_keyboard(lang: str = "uz_latn") -> ReplyKeyboardMarkup:
    """Build simple cancel keyboard."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("btn_cancel", lang=lang))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
