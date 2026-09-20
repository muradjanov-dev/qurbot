"""Visitor checkout and operator inbox labels."""

_LABELS = {
    "delivery_confirm": (
        "Bu manzilga yetkazishni operator bilan aniqlashtiring.",
        "Бу манзилга етказишни оператор билан аниқлаштиринг.",
        "Уточните доставку по этому адресу у оператора.",
    ),
    "session_error": (
        "Ulanib bo'lmadi. Cookie ruxsatini tekshirib, sahifani yangilang.",
        "Уланиб бўлмади. Cookie рухсатини текшириб, саҳифани янгиланг.",
        "Не удалось подключиться. Разрешите cookie и обновите страницу.",
    ),
    "inbox": ("Suhbatlar", "Суҳбатлар", "Обращения"),
    "admin_login": ("Administrator kirishi", "Администратор кириши", "Вход для администратора"),
    "waiting": ("Kutayotganlar", "Кутаётганлар", "Ожидают"),
    "mine": ("Mening suhbatlarim", "Менинг суҳбатларим", "Мои чаты"),
    "others": ("Boshqa operatorlar", "Бошқа операторлар", "Другие операторы"),
    "empty": ("Hozircha murojaat yo'q", "Ҳозирча мурожаат йўқ", "Обращений пока нет"),
    "select": ("Chapdan suhbatni tanlang", "Чапдан суҳбатни танланг", "Выберите чат слева"),
    "customer": ("Mijoz", "Мижоз", "Клиент"),
    "claim": ("Qabul qilish", "Қабул қилиш", "Принять"),
    "finish": ("Yakunlash → AI", "Якунлаш → AI", "Завершить → AI"),
    "finish_confirm": (
        "Suhbatni yakunlab, AI yordamchiga qaytarasizmi?",
        "Суҳбатни якунлаб, AI ёрдамчига қайтарасизми?",
        "Завершить обращение и вернуть AI-помощнику?",
    ),
    "handoff_confirm": (
        "Operatorni suhbatga chaqirasizmi?",
        "Операторни суҳбатга чақирасизми?",
        "Пригласить оператора в чат?",
    ),
    "more": ("Yana ko'rsatish", "Яна кўрсатиш", "Показать ещё"),
    "back": ("Orqaga", "Орқага", "Назад"),
    "close": ("Yopish", "Ёпиш", "Закрыть"),
    "cart": ("Savat", "Сават", "Корзина"),
    "remove": ("O'chirish", "Ўчириш", "Удалить"),
    "name": ("Ismingiz", "Исмингиз", "Ваше имя"),
    "phone": ("Telefon", "Телефон", "Телефон"),
    "address": ("Yetkazish manzili", "Етказиш манзили", "Адрес доставки"),
    "district": ("Tuman", "Туман", "Район"),
    "calculate": ("Jami narxni hisoblash", "Жами нархни ҳисоблаш", "Рассчитать итог"),
    "confirm": ("Buyurtmani tasdiqlash", "Буюртмани тасдиқлаш", "Подтвердить заказ"),
    "ordered": ("Buyurtma qabul qilindi", "Буюртма қабул қилинди", "Заказ принят"),
    "orders": ("Buyurtmalarim", "Буюртмаларим", "Мои заказы"),
    "empty_cart": ("Savatingiz hali bo'sh", "Саватингиз ҳали бўш", "Ваша корзина пока пуста"),
    "delivery": ("Yetkazib berish", "Етказиб бериш", "Доставка"),
    "total": ("Jami", "Жами", "Итого"),
    "guest_hint": (
        "Ro'yxatdan o'tish shart emas. Tarix shu brauzerda saqlanadi.",
        "Рўйхатдан ўтиш шарт эмас. Тарих шу браузерда сақланади.",
        "Регистрация не нужна. История доступна в этом браузере.",
    ),
    "limit": (
        "Xabarlar limiti tugadi. Keyinroq yozing yoki operatorga murojaat qiling.",
        "Хабарлар лимити тугади. Кейинроқ ёзинг ёки операторга мурожаат қилинг.",
        "Лимит сообщений исчерпан. Напишите позже или обратитесь к оператору.",
    ),
    "new_request": (
        "Yangi murojaat. Javob berish uchun suhbatlar sahifasini oching.",
        "Янги мурожаат. Жавоб бериш учун суҳбатлар саҳифасини очинг.",
        "Новое обращение. Откройте страницу обращений, чтобы ответить.",
    ),
}

SALES_MESSAGES = {
    f"sales_{key}": dict(zip(("uz_latn", "uz_cyrl", "ru"), values, strict=True))
    for key, values in _LABELS.items()
}
