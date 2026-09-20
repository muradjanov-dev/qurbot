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

_LABELS.update(
    {
        "price_request": ("Narxi kelishiladi", "Нархи келишилади", "Цена по запросу"),
        "request_hint": (
            "Narx yoki mavjudlikni operator aniqlashtiradi. "
            "Butun savat bitta ariza bo'lib yuboriladi.",
            "Нарх ёки мавжудликни оператор аниқлаштиради. Бутун сават битта ариза бўлиб юборилади.",
            "Оператор уточнит цену и наличие. Вся корзина будет отправлена одной заявкой.",
        ),
        "send_request": ("Operatorga yuborish", "Операторга юбориш", "Отправить оператору"),
        "request_sent": (
            "Ariza #{id} operatorga yuborildi. Narx va mavjudlik hali tasdiqlanmagan.",
            "Ариза #{id} операторга юборилди. Нарх ва мавжудлик ҳали тасдиқланмаган.",
            "Заявка №{id} отправлена оператору. Цена и наличие ещё не подтверждены.",
        ),
        "requests": ("Arizalarim", "Аризаларим", "Мои заявки"),
        "request_open": (
            "Operator bilan kelishilmoqda",
            "Оператор билан келишилмоқда",
            "На согласовании",
        ),
        "request_agreed": ("Kelishildi", "Келишилди", "Согласовано"),
        "request_cancelled": ("Bekor qilindi", "Бекор қилинди", "Отменено"),
        "resolution_note": (
            "Kelishuv yoki bekor qilish izohi",
            "Келишув ёки бекор қилиш изоҳи",
            "Комментарий к результату",
        ),
        "resolve_first": (
            "Avval ochiq arizalar natijasini belgilang.",
            "Аввал очиқ аризалар натижасини белгиланг.",
            "Сначала укажите результат открытых заявок.",
        ),
        "more_products": ("Yana mahsulot qo'shish", "Яна маҳсулот қўшиш", "Добавить ещё товар"),
        "view_cart": ("Savatga o'tish", "Саватга ўтиш", "Перейти в корзину"),
        "back_chat": ("Suhbatga qaytish", "Суҳбатга қайтиш", "Вернуться в чат"),
        "back_variants": ("Variantlarga qaytish", "Вариантларга қайтиш", "Назад к вариантам"),
        "custom_qty": ("Boshqa miqdor", "Бошқа миқдор", "Другое количество"),
        "enter_qty": (
            "Nechta {unit} kerak? Masalan: 155",
            "Нечта {unit} керак? Масалан: 155",
            "Сколько {unit} нужно? Например: 155",
        ),
        "edit_qty": ("Miqdorni o'zgartirish", "Миқдорни ўзгартириш", "Изменить количество"),
        "in_cart": (
            "{name} — {qty} {unit} savatda.",
            "{name} — {qty} {unit} саватда.",
            "В корзине: {name} — {qty} {unit}.",
        ),
        "search_prompt": (
            "Yana nima kerak? Mahsulot nomini yozing.",
            "Яна нима керак? Маҳсулот номини ёзинг.",
            "Что ещё нужно? Напишите название товара.",
        ),
        "choose_product": ("Mahsulot tanlash", "Маҳсулот танлаш", "Выбрать товар"),
        "contact_prompt": ("{field} kiriting:", "{field} киритинг:", "Укажите: {field}"),
        "contact_confirm": (
            "Ma'lumotlarni tasdiqlash",
            "Маълумотларни тасдиқлаш",
            "Подтвердить данные",
        ),
        "contact_edit": (
            "Ma'lumotlarni o'zgartirish",
            "Маълумотларни ўзгартириш",
            "Изменить данные",
        ),
        "known_sum": (
            "Narxi ma'lum qatorlar summasi (yakuniy jami emas)",
            "Нархи маълум қаторлар суммаси (якуний жами эмас)",
            "Сумма известных цен (не окончательный итог)",
        ),
        "progress_queued": ("Navbatda", "Навбатда", "В очереди"),
        "progress_running": ("AI javob tayyorlamoqda", "AI жавоб тайёрламоқда", "AI готовит ответ"),
        "progress_ready": (
            "Javob tayyor. Suhbatni davom ettirishingiz mumkin.",
            "Жавоб тайёр. Суҳбатни давом эттиришингиз мумкин.",
            "Ответ готов. Можно продолжить разговор.",
        ),
        "progress_slow": (
            "Javob odatdagidan uzoqroq kutilmoqda. Operatorni chaqirishingiz mumkin.",
            "Жавоб одатдагидан узоқроқ кутилмоқда. Операторни чақиришингиз мумкин.",
            "Ответ занимает больше времени. Можно обратиться к оператору.",
        ),
        "progress_0": ("Qabul qildik, xo'jayin 🙂", "Қабул қилдик, хўжайин 🙂", "Принято, шеф 🙂"),
        "progress_1": (
            "So'rovingiz bizda — xabarni qayta yuborish shart emas.",
            "Сўровингиз бизда — хабарни қайта юбориш шарт эмас.",
            "Запрос у нас — повторно отправлять его не нужно.",
        ),
        "progress_2": (
            "Bir oz sabr 🙂 Javob shu suhbatga keladi.",
            "Бир оз сабр 🙂 Жавоб шу суҳбатга келади.",
            "Немного терпения 🙂 Ответ появится в этом чате.",
        ),
        "progress_3": (
            "Yordamchidan javob kelishini kutyapmiz.",
            "Ёрдамчидан жавоб келишини кутяпмиз.",
            "Ждём ответ помощника.",
        ),
        "progress_4": (
            "Keyingi qadamni ham ko'rsatamiz — yolg'iz qoldirmaymiz 🙂",
            "Кейинги қадамни ҳам кўрсатамиз — ёлғиз қолдирмаймиз 🙂",
            "Подскажем и следующий шаг — не оставим без помощи 🙂",
        ),
        "progress_5": (
            "Savolingiz e'tiborsiz qolmadi, xo'jayin.",
            "Саволингиз эътиборсиз қолмади, хўжайин.",
            "Ваш вопрос не остался без внимания, шеф.",
        ),
        "progress_6": (
            "Kutayotganingiz uchun rahmat! Suhbat shu yerda davom etadi.",
            "Кутаётганингиз учун раҳмат! Суҳбат шу ерда давом этади.",
            "Спасибо за ожидание! Продолжим разговор здесь.",
        ),
    }
)

SALES_MESSAGES = {
    f"sales_{key}": dict(zip(("uz_latn", "uz_cyrl", "ru"), values, strict=True))
    for key, values in _LABELS.items()
}
