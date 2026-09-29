"""Shared Tezqur navigation and identity labels."""

_LABELS = {
    "dashboard": ("Umumiy ko‘rinish", "Умумий кўриниш", "Обзор"),
    "products": ("Mahsulotlar", "Маҳсулотлар", "Товары"),
    "customers": ("Mijozlar", "Мижозлар", "Клиенты"),
    "settings": ("Sozlamalar", "Созламалар", "Настройки"),
    "telegram_login": ("Telegram orqali kirish", "Telegram орқали кириш", "Войти через Telegram"),
    "guest": ("Mehmon rejimi", "Меҳмон режими", "Гостевой режим"),
    "admin": ("Administrator", "Администратор", "Администратор"),
    "customer_view": ("Mijoz ko‘rinishi", "Мижоз кўриниши", "Витрина"),
    "admin_menu": ("Boshqaruv menyusi", "Бошқарув менюси", "Меню управления"),
    "permission_title": (
        "Administrator huquqi kerak",
        "Администратор ҳуқуқи керак",
        "Нужны права администратора",
    ),
    "permission_body": (
        "Bu bo‘lim administratorlar uchun. Boshqa Telegram hisobingiz bilan kirishingiz mumkin.",
        "Бу бўлим администраторлар учун. Бошқа Telegram ҳисобингиз билан киришингиз мумкин.",
        "Этот раздел доступен администраторам. Можно войти с другим аккаунтом Telegram.",
    ),
    "switch_account": ("Hisobni almashtirish", "Ҳисобни алмаштириш", "Сменить аккаунт"),
    "currency": ("Valyuta", "Валюта", "Валюта"),
    "file_currency": ("Fayldagi narx valyutasi", "Файлдаги нарх валютаси", "Валюта цен в файле"),
    "currency_column": (
        "Faylning valyuta ustunidan",
        "Файлнинг валюта устунидан",
        "Из столбца валюты в файле",
    ),
    "currency_import_hint": (
        "Valyuta ustuni bo‘lmasa, barcha qatorlar uchun UZS yoki USDni tanlang.",
        "Валюта устуни бўлмаса, барча қаторлар учун UZS ёки USDни танланг.",
        "Если столбца валюты нет, выберите UZS или USD для всех строк.",
    ),
    "currency_unknown": (
        "Valyutasi aniqlanmagan qatorlar qo‘llanmaydi.",
        "Валютаси аниқланмаган қаторлар қўлланмайди.",
        "Строки с неизвестной валютой не будут применены.",
    ),
}
UI_MESSAGES = {
    f"ui_{key}": dict(zip(("uz_latn", "uz_cyrl", "ru"), value, strict=True))
    for key, value in _LABELS.items()
}
