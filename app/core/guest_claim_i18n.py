"""Localized copy for guest-cart claims and saved-cart review."""

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
    "legacy_cart_source_title": {
        "uz_latn": "Oldingi savatdan saqlangan mahsulotlar",
        "uz_cyrl": "Аввалги саватдан сақланган маҳсулотлар",
        "ru": "Сохранённые товары из прежней корзины",
    },
    "legacy_cart_review_hint": {
        "uz_latn": (
            "Hisob savatiga qo‘shilmagan mahsulotlarni tekshiring. "
            "Belgilanganlarini o‘chirishingiz "
            "yoki qolganlarini hisob savati bilan birlashtirishga qayta urinishingiz mumkin. "
            "Hisob savatidagi mahsulotni qoldirmoqchi bo‘lsangiz, unga mos saqlangan mahsulotni "
            "belgilang. Saqlangan mahsulotni qoldirish uchun esa hisob savatidagi mos kelmaydigan "
            "qatorni o‘chirib, qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Ҳисоб саватига қўшилмаган маҳсулотларни текширинг. Белгиланганларини ўчиришингиз "
            "ёки қолганларини ҳисоб савати билан бирлаштиришга қайта уринишингиз мумкин. "
            "Ҳисоб саватидаги маҳсулотни қолдирмоқчи бўлсангиз, унга мос сақланган маҳсулотни "
            "белгиланг. Сақланган маҳсулотни қолдириш учун эса ҳисоб саватидаги мос келмайдиган "
            "қаторни ўчириб, қайта уриниб кўринг."
        ),
        "ru": (
            "Проверьте товары, которые не добавились в корзину аккаунта. Отмеченные можно удалить, "
            "а для остальных повторить объединение. Чтобы оставить товар из корзины аккаунта, "
            "отметьте соответствующий сохранённый товар. Чтобы оставить сохранённый товар, "
            "удалите несовместимую позицию из корзины аккаунта ниже и повторите попытку."
        ),
    },
    "legacy_cart_drop_item": {
        "uz_latn": "Saqlangan savatdan olib tashlash",
        "uz_cyrl": "Сақланган саватдан олиб ташлаш",
        "ru": "Удалить из сохранённой корзины",
    },
    "legacy_cart_retry": {
        "uz_latn": "Birlashtirishni qayta urinish",
        "uz_cyrl": "Бирлаштиришни қайта уриниш",
        "ru": "Повторить объединение",
    },
    "legacy_cart_drop_selected": {
        "uz_latn": "Tanlangan mahsulotlarni o‘chirish",
        "uz_cyrl": "Танланган маҳсулотларни ўчириш",
        "ru": "Удалить выбранные товары",
    },
    "legacy_cart_retrying": {
        "uz_latn": "Savat yangilanmoqda…",
        "uz_cyrl": "Сават янгиланмоқда…",
        "ru": "Обновляем корзину…",
    },
    "legacy_cart_review_failed": {
        "uz_latn": (
            "Mahsulotlar birlashtirilmadi. Saqlangan mahsulotlar shu yerda turibdi; "
            "yana urinib ko‘rishingiz mumkin."
        ),
        "uz_cyrl": (
            "Маҳсулотлар бирлаштирилмади. Сақланган маҳсулотлар шу ерда турибди; "
            "яна уриниб кўришингиз мумкин."
        ),
        "ru": (
            "Товары не удалось объединить. Сохранённые товары остались здесь; "
            "можно попробовать ещё раз."
        ),
    },
    "legacy_cart_review_conflict": {
        "uz_latn": (
            "Bir xil mahsulot turli o‘lchov birliklarida ko‘rsatilgan. Hisob savatidagi qatorni "
            "qoldirish uchun saqlangan qatorni o‘chiring. Saqlangan qatorni qoldirish uchun esa "
            "quyidagi hisob savatidan mos kelmaydigan qatorni o‘chirib, qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Бир хил маҳсулот турли ўлчов бирликларида кўрсатилган. Ҳисоб саватидаги қаторни "
            "қолдириш учун сақланган қаторни ўчиринг. Сақланган қаторни қолдириш учун эса "
            "қуйидаги ҳисоб саватидан мос келмайдиган қаторни ўчириб, қайта уриниб кўринг."
        ),
        "ru": (
            "Один и тот же товар указан в разных единицах измерения. Чтобы оставить позицию "
            "из корзины аккаунта, удалите сохранённую позицию. Чтобы оставить сохранённую, "
            "удалите несовместимую позицию из корзины ниже и повторите попытку."
        ),
    },
    "legacy_cart_review_changed": {
        "uz_latn": (
            "Saqlangan savat boshqa oynada o‘zgardi. Yangilangan ro‘yxatni tekshirib, "
            "kerak bo‘lsa qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Сақланган сават бошқа ойнада ўзгарди. Янгиланган рўйхатни текшириб, "
            "керак бўлса қайта уриниб кўринг."
        ),
        "ru": (
            "Сохранённая корзина изменилась в другой вкладке. Проверьте обновлённый список "
            "и при необходимости повторите попытку."
        ),
    },
    "legacy_cart_discarded": {
        "uz_latn": (
            "Belgilangan mahsulotlar o‘chirildi. Qolganlarini birlashtirishga "
            "qayta urinishingiz mumkin."
        ),
        "uz_cyrl": (
            "Белгиланган маҳсулотлар ўчирилди. Қолганларини бирлаштиришга қайта уринишингиз мумкин."
        ),
        "ru": ("Выбранные товары удалены. Для остальных можно повторить объединение."),
    },
    "legacy_cart_storage_failed": {
        "uz_latn": (
            "Tanlangan mahsulotlarni saqlangan savatdan o‘chirib bo‘lmadi. "
            "Sahifani yangilab qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Танланган маҳсулотларни сақланган саватдан ўчириб бўлмади. "
            "Саҳифани янгилаб қайта уриниб кўринг."
        ),
        "ru": (
            "Не удалось удалить выбранные товары из сохранённой корзины. "
            "Обновите страницу и попробуйте ещё раз."
        ),
    },
}
