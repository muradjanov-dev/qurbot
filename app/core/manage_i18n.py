"""Labels for the unified storefront admin panel."""

_LABELS = {
    "title": ("Boshqaruv", "Бошқарув", "Управление"),
    "new_product": ("Yangi katalog mahsuloti", "Янги каталог маҳсулоти", "Новый товар каталога"),
    "offer": ("Narx va qoldiq qo'shish", "Нарх ва қолдиқ қўшиш", "Добавить цену и наличие"),
    "name": ("Mahsulot nomi", "Маҳсулот номи", "Название товара"),
    "category": ("Toifa", "Тоифа", "Категория"),
    "unit": ("Birlik", "Бирлик", "Единица"),
    "size": ("O'lcham", "Ўлчам", "Размер"),
    "thickness": ("Qalinlik (mm)", "Қалинлик (мм)", "Толщина (мм)"),
    "brand": ("Brend", "Бренд", "Бренд"),
    "description": ("Tavsif", "Тавсиф", "Описание"),
    "photo": ("Rasm", "Расм", "Фото"),
    "stock": ("Mavjudlik", "Мавжудлик", "Наличие"),
    "pack": ("Qadoq miqdori", "Қадоқ миқдори", "Количество в упаковке"),
    "confirm_new": (
        "O'xshash mahsulot bor. Baribir yangisini yaratish",
        "Ўхшаш маҳсулот бор. Барибир янгисини яратиш",
        "Похожий товар существует. Создать новый",
    ),
    "duplicate": (
        "O'xshash mahsulot topildi. Uni tanlang yoki yangi variant ekanini tasdiqlang.",
        "Ўхшаш маҳсулот топилди. Уни танланг ёки янги вариант эканини тасдиқланг.",
        "Найден похожий товар. Выберите его или подтвердите новый вариант.",
    ),
    "invalid": ("Ma'lumotlarni tekshiring.", "Маълумотларни текширинг.", "Проверьте данные."),
    "admins": ("Adminlar", "Админлар", "Администраторы"),
    "promote": ("Admin qilish", "Админ қилиш", "Назначить администратором"),
    "users": ("Foydalanuvchilar", "Фойдаланувчилар", "Пользователи"),
    "active": ("Faol", "Фаол", "Активен"),
    "aliases": ("Aliaslar", "Алиаслар", "Псевдонимы"),
    "photos": ("Rasm tekshiruvi", "Расм текшируви", "Проверка фото"),
    "optional": ("ixtiyoriy", "ихтиёрий", "необязательно"),
    "uz_cyrl_name": ("O'zbekcha (kirill)", "Ўзбекча (кирилл)", "Узбекский (кириллица)"),
    "ru_name": ("Ruscha", "Русча", "Русский"),
    "telegram_id": ("Telegram raqami", "Telegram рақами", "Telegram ID"),
    "gmv": ("Buyurtmalar qiymati", "Буюртмалар қиймати", "Стоимость заказов"),
    "district_required": (
        "Yetkazish tumanini tanlang.",
        "Етказиш туманини танланг.",
        "Выберите район доставки.",
    ),
}

MANAGE_MESSAGES = {
    f"manage_{key}": dict(zip(("uz_latn", "uz_cyrl", "ru"), values, strict=True))
    for key, values in _LABELS.items()
}
