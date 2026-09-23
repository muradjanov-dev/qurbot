"""Visitor checkout and operator inbox labels."""

_LABELS = {
    "address_invalid": (
        "Yetkazish manzilini to'liqroq yozing (kamida 5 belgi).",
        "Етказиш манзилини тўлиқроқ ёзинг (камида 5 белги).",
        "Укажите адрес доставки подробнее (не менее 5 символов).",
    ),
    "contact_invalid": (
        "Ism, telefon, tuman va yetkazish manzilini tekshiring.",
        "Исм, телефон, туман ва етказиш манзилини текширинг.",
        "Проверьте имя, телефон, район и адрес доставки.",
    ),
    "phone_invalid": (
        "Telefon raqamini +998 bilan to'liq kiriting.",
        "Телефон рақамини +998 билан тўлиқ киритинг.",
        "Введите полный номер телефона с +998.",
    ),
    "name_invalid": ("Ismingizni kiriting.", "Исмингизни киритинг.", "Введите имя."),
    "district_invalid": ("Tumanni tanlang.", "Туманни танланг.", "Выберите район."),
    "delivery_confirm": (
        "Bu manzilga yetkazishni operator bilan aniqlashtiring.",
        "Бу манзилга етказишни оператор билан аниқлаштиринг.",
        "Уточните доставку по этому адресу у оператора.",
    ),
    "session_error": (
        "Kirish sessiyasini ochib bo'lmadi. Ilovani yopib, botdagi tugmadan qayta oching.",
        "Кириш сессиясини очиб бўлмади. Иловани ёпиб, ботдаги тугмадан қайта очинг.",
        "Не удалось открыть сеанс. Закройте приложение и откройте его снова кнопкой в боте.",
    ),
    "inbox": ("Suhbatlar", "Суҳбатлар", "Обращения"),
    "admin_login": ("Administrator kirishi", "Администратор кириши", "Вход для администратора"),
    "waiting": ("Kutayotganlar", "Кутаётганлар", "Ожидают"),
    "mine": ("Mening suhbatlarim", "Менинг суҳбатларим", "Мои чаты"),
    "others": ("Boshqa operatorlar", "Бошқа операторлар", "Другие операторы"),
    "empty": ("Hozircha murojaat yo'q", "Ҳозирча мурожаат йўқ", "Обращений пока нет"),
    "select": ("Chapdan suhbatni tanlang", "Чапдан суҳбатни танланг", "Выберите чат слева"),
    "customer": ("Mijoz", "Мижоз", "Клиент"),
    "claim": ("✋ Qabul qilish", "✋ Қабул қилиш", "✋ Принять"),
    "finish": ("✅ Yakunlash → AI", "✅ Якунлаш → AI", "✅ Завершить → AI"),
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
    "back": ("◀️ Orqaga", "◀️ Орқага", "◀️ Назад"),
    "close": ("✖️ Yopish", "✖️ Ёпиш", "✖️ Закрыть"),
    "cart": ("Savat", "Сават", "Корзина"),
    "remove": ("🗑 O'chirish", "🗑 Ўчириш", "🗑 Удалить"),
    "name": ("Ismingiz", "Исмингиз", "Ваше имя"),
    "phone": ("Telefon", "Телефон", "Телефон"),
    "address": ("Yetkazish manzili", "Етказиш манзили", "Адрес доставки"),
    "district": ("Tuman", "Туман", "Район"),
    "calculate": ("🧮 Jami narxni hisoblash", "🧮 Жами нархни ҳисоблаш", "🧮 Рассчитать итог"),
    "confirm": ("✅ Buyurtmani tasdiqlash", "✅ Буюртмани тасдиқлаш", "✅ Подтвердить заказ"),
    "ordered": ("Buyurtma qabul qilindi", "Буюртма қабул қилинди", "Заказ принят"),
    "orders": ("📦 Buyurtmalarim", "📦 Буюртмаларим", "📦 Мои заказы"),
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
        "send_request": (
            "📨 Operatorga yuborish",
            "📨 Операторга юбориш",
            "📨 Отправить оператору",
        ),
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
        "more_products": (
            "🔍 Yana mahsulot qo'shish",
            "🔍 Яна маҳсулот қўшиш",
            "🔍 Добавить ещё товар",
        ),
        "view_cart": ("🛒 Savatga o'tish", "🛒 Саватга ўтиш", "🛒 Перейти в корзину"),
        "back_chat": ("Suhbatga qaytish", "Суҳбатга қайтиш", "Вернуться в чат"),
        "back_variants": ("↩️ Variantlarga qaytish", "↩️ Вариантларга қайтиш", "↩️ Назад к вариантам"),
        "custom_qty": ("✏️ Boshqa miqdor", "✏️ Бошқа миқдор", "✏️ Другое количество"),
        "enter_qty": (
            "Nechta {unit} kerak? Masalan: 155",
            "Нечта {unit} керак? Масалан: 155",
            "Сколько {unit} нужно? Например: 155",
        ),
        "edit_qty": ("✏️ Miqdorni o'zgartirish", "✏️ Миқдорни ўзгартириш", "✏️ Изменить количество"),
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
        "progress_queued": (
            "📥 Qabul qildik, xo'jayin!",
            "📥 Қабул қилдик, хўжайин!",
            "📥 Приняли, шеф!",
        ),
        "progress_running": (
            "⚡ Siz uchun ishlayapmiz…",
            "⚡ Сиз учун ишлаяпмиз…",
            "⚡ Работаем для вас…",
        ),
        "progress_ready": (
            "✅ Javob tayyor! Suhbatni davom ettiravering.",
            "✅ Жавоб тайёр! Суҳбатни давом эттираверинг.",
            "✅ Ответ готов! Можно продолжить разговор.",
        ),
        "progress_slow": (
            "⏳ Bu savol biroz ko'proq vaqt olyapti. Xohlasangiz, operatorni chaqiramiz 👤",
            "⏳ Бу савол бироз кўпроқ вақт оляпти. Хоҳласангиз, операторни чақирамиз 👤",
            "⏳ Этот вопрос занимает чуть больше времени. Если хотите, позовём оператора 👤",
        ),
        "progress_0": (
            "🔍 Katalogni siz uchun varaqlayapmiz…",
            "🔍 Каталогни сиз учун варақлаяпмиз…",
            "🔍 Листаем каталог для вас…",
        ),
        "progress_1": (
            "📝 So'rovingiz bizda — qayta yuborish shart emas.",
            "📝 Сўровингиз бизда — қайта юбориш шарт эмас.",
            "📝 Запрос у нас — повторять не нужно.",
        ),
        "progress_2": (
            "🧱 Mos mahsulotlarni tanlab chiqyapmiz…",
            "🧱 Мос маҳсулотларни танлаб чиқяпмиз…",
            "🧱 Подбираем подходящие товары…",
        ),
        "progress_3": (
            "📏 O'lcham va birliklarni tekshiryapmiz…",
            "📏 Ўлчам ва бирликларни текширяпмиз…",
            "📏 Проверяем размеры и единицы…",
        ),
        "progress_4": (
            "🛠 Keyingi qadamni ham ko'rsatamiz — yolg'iz qoldirmaymiz!",
            "🛠 Кейинги қадамни ҳам кўрсатамиз — ёлғиз қолдирмаймиз!",
            "🛠 Подскажем и следующий шаг — не оставим без помощи!",
        ),
        "progress_5": (
            "🚚 Narx va yetkazishni hisoblayapmiz…",
            "🚚 Нарх ва етказишни ҳисоблаяпмиз…",
            "🚚 Считаем цену и доставку…",
        ),
        "progress_6": (
            "🙏 Sabringiz uchun rahmat! Javob shu yerda chiqadi.",
            "🙏 Сабрингиз учун раҳмат! Жавоб шу ерда чиқади.",
            "🙏 Спасибо за ожидание! Ответ появится здесь.",
        ),
        "progress_7": (
            "📦 Omborda bor-yo'qligini aniqlayapmiz…",
            "📦 Омборда бор-йўқлигини аниқлаяпмиз…",
            "📦 Уточняем наличие на складе…",
        ),
        "progress_8": (
            "⚙️ So'rovingizni katalog bilan solishtiryapmiz…",
            "⚙️ Сўровингизни каталог билан солиштиряпмиз…",
            "⚙️ Сверяем запрос с каталогом…",
        ),
        "progress_9": (
            "💬 Javobni tayyorlayapmiz, bir zum…",
            "💬 Жавобни тайёрлаяпмиз, бир зум…",
            "💬 Готовим ответ, одну секунду…",
        ),
        "progress_10": (
            "🏗 Quruvchining vaqti qimmat — tezlashtiryapmiz!",
            "🏗 Қурувчининг вақти қиммат — тезлаштиряпмиз!",
            "🏗 Время строителя дорого — ускоряемся!",
        ),
        "progress_11": (
            "🧮 Hisob-kitob ketyapti, adashmaymiz…",
            "🧮 Ҳисоб-китоб кетяпти, адашмаймиз…",
            "🧮 Идёт расчёт, не ошибёмся…",
        ),
        "progress_12": (
            "☕ Bir piyola choy ichguncha tayyor bo'lamiz.",
            "☕ Бир пиёла чой ичгунча тайёр бўламиз.",
            "☕ Управимся, пока вы пьёте чай.",
        ),
        "progress_13": (
            "🤝 Ishonchli qo'ldasiz — hammasi nazoratda.",
            "🤝 Ишончли қўлдасиз — ҳаммаси назоратда.",
            "🤝 Вы в надёжных руках — всё под контролем.",
        ),
        "progress_14": (
            "📊 Takliflarni solishtirib, eng qulayini tanlayapmiz…",
            "📊 Таклифларни солиштириб, энг қулайини танлаяпмиз…",
            "📊 Сравниваем предложения и выбираем лучшее…",
        ),
        "progress_15": (
            "🔧 Oxirgi boltni burab qo'yyapmiz…",
            "🔧 Охирги болтни бураб қўйяпмиз…",
            "🔧 Закручиваем последний болт…",
        ),
        "progress_16": (
            "🗂 Ro'yxatingizni qator-qator ko'rib chiqyapmiz…",
            "🗂 Рўйхатингизни қатор-қатор кўриб чиқяпмиз…",
            "🗂 Просматриваем ваш список строка за строкой…",
        ),
        "progress_17": (
            "⏱ Yana bir necha soniya — deyarli tayyor.",
            "⏱ Яна бир неча сония — деярли тайёр.",
            "⏱ Ещё пара секунд — почти готово.",
        ),
        "progress_18": (
            "🎯 Aynan kerakli turini topyapmiz…",
            "🎯 Айнан керакли турини топяпмиз…",
            "🎯 Ищем именно нужный вариант…",
        ),
        "progress_19": (
            "💡 Siz uchun eng foydali variantni o'ylayapmiz…",
            "💡 Сиз учун энг фойдали вариантни ўйлаяпмиз…",
            "💡 Продумываем самый выгодный вариант для вас…",
        ),
        "progress_20": (
            "🚀 Deyarli tayyor, tayyorlaning!",
            "🚀 Деярли тайёр, тайёрланинг!",
            "🚀 Почти готово, приготовьтесь!",
        ),
    }
)

SALES_MESSAGES = {
    f"sales_{key}": dict(zip(("uz_latn", "uz_cyrl", "ru"), values, strict=True))
    for key, values in _LABELS.items()
}
