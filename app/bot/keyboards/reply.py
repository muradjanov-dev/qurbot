from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.i18n import t


def get_main_menu_keyboard(
    lang: str = "uz_latn", is_shop_owner: bool = False
) -> ReplyKeyboardMarkup:
    """Build main menu reply keyboard.

    "Ro'yxat yuborish" gets its own full-width row because it is the primary
    action -- everything else in the menu exists to support it.
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("menu_send_list", lang=lang))
    builder.button(text=t("menu_price_check", lang=lang))
    builder.button(text=t("menu_cabinet", lang=lang))
    if is_shop_owner:
        builder.button(text=t("menu_shop_portal", lang=lang))
        builder.adjust(1, 2, 1)
    else:
        builder.adjust(1, 2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_cabinet_keyboard(lang: str = "uz_latn") -> ReplyKeyboardMarkup:
    """Build the cabinet submenu: orders, settings, and a way back."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("menu_my_orders", lang=lang))
    builder.button(text=t("menu_settings", lang=lang))
    builder.button(text=t("btn_main_menu", lang=lang))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_shop_panel_keyboard(lang: str = "uz_latn") -> ReplyKeyboardMarkup:
    """Build the shop-owner panel keyboard.

    Carries the entry point for the product upload wizard, which is otherwise
    unreachable -- its handler matches on this button's exact text.
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text=t("menu_add_product", lang=lang))
    builder.button(text=t("btn_main_menu", lang=lang))
    builder.adjust(1, 1)
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
