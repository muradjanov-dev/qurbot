"""Localized copy for reviewing a browser's guest-cart claim."""

GUEST_CLAIM_MESSAGES: dict[str, dict[str, str]] = {
    "guest_claim_source_title": {
        "uz_latn": "Mehmon savatidagi mahsulotlar",
        "uz_cyrl": "Меҳмон саватидаги маҳсулотлар",
        "ru": "Товары из гостевой корзины",
    },
    "guest_claim_review_hint": {
        "uz_latn": (
            "Mehmon savatidagi mahsulotlarni ko‘ring. Belgilagan qatorlaringiz olib tashlanadi; "
            "qolganlari hisob savatiga qo‘shiladi. Hisob savatidagi qatorni qoldirmoqchi "
            "bo‘lsangiz, unga mos keladigan mehmon qatorini belgilang. Mehmon qatorini "
            "qoldirish uchun esa pastdagi hisob savatidan mos kelmaydigan qatorni o‘chirib, "
            "qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Меҳмон саватидаги маҳсулотларни кўринг. Белгиланган қаторлар олиб ташланади; "
            "қолганлари аккаунт саватига қўшилади. Аккаунт саватидаги қаторни қолдирмоқчи "
            "бўлсангиз, унга мос меҳмон қаторини белгиланг. Меҳмон қаторини қолдириш учун "
            "эса қуйидаги аккаунт саватидан мос келмайдиган қаторни ўчириб, қайта уриниб кўринг."
        ),
        "ru": (
            "Проверьте товары из гостевой корзины. Отмеченные позиции будут удалены, "
            "остальные добавятся в корзину аккаунта. Чтобы оставить позицию из корзины "
            "аккаунта, отметьте соответствующую гостевую позицию. Чтобы оставить гостевую, "
            "удалите конфликтующую позицию из корзины аккаунта ниже и повторите попытку."
        ),
    },
    "guest_claim_drop_item": {
        "uz_latn": "Mehmon savatidan olib tashlash",
        "uz_cyrl": "Меҳмон саватидан олиб ташлаш",
        "ru": "Удалить из гостевой корзины",
    },
    "guest_claim_requires_confirmation": {
        "uz_latn": "Narx yoki mavjudlikni operator tasdiqlashi kerak",
        "uz_cyrl": "Нарх ёки мавжудликни оператор тасдиқлаши керак",
        "ru": "Цену или наличие должен подтвердить оператор",
    },
    "guest_claim_merge": {
        "uz_latn": "Birlashtirishni qayta urinish",
        "uz_cyrl": "Бирлаштиришни қайта уриниш",
        "ru": "Повторить объединение",
    },
    "guest_claim_drop_selected": {
        "uz_latn": "Tanlangan mehmon qatorlarini olib tashlab birlashtirish",
        "uz_cyrl": "Танланган меҳмон қаторларини олиб ташлаб бирлаштириш",
        "ru": "Удалить выбранные гостевые позиции и объединить",
    },
    "guest_claim_empty": {
        "uz_latn": "Mehmon savatida mahsulot qolmagan.",
        "uz_cyrl": "Меҳмон саватида маҳсулот қолмаган.",
        "ru": "В гостевой корзине не осталось товаров.",
    },
    "guest_claim_preview_loading": {
        "uz_latn": "Mehmon savati yuklanmoqda…",
        "uz_cyrl": "Меҳмон савати юкланмоқда…",
        "ru": "Загружаем гостевую корзину…",
    },
    "guest_claim_preview_failed": {
        "uz_latn": "Mehmon savatini ko‘rib bo‘lmadi. Sahifani yangilang.",
        "uz_cyrl": "Меҳмон саватини кўриб бўлмади. Саҳифани янгиланг.",
        "ru": "Не удалось показать гостевую корзину. Обновите страницу.",
    },
    "guest_claim_still_conflicts": {
        "uz_latn": (
            "Savatlar mos kelmadi. Mehmon qatorini belgilang yoki pastdagi savatdan "
            "mos kelmaydigan qatorni o‘chirib, qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Саватлар мос келмади. Меҳмон қаторини белгиланг ёки қуйидаги саватдан "
            "мос келмайдиган қаторни ўчириб, қайта уриниб кўринг."
        ),
        "ru": (
            "Корзины не удалось объединить. Отметьте гостевую позицию или удалите "
            "несовместимую позицию из корзины ниже и повторите попытку."
        ),
    },
    "guest_claim_selection_invalid": {
        "uz_latn": "Tanlangan qatorlar yangilangan. Ro‘yxatni tekshirib qayta tanlang.",
        "uz_cyrl": "Танланган қаторлар янгиланган. Рўйхатни текшириб қайта танланг.",
        "ru": "Список изменился. Проверьте его и выберите позиции заново.",
    },
}
