"""Storefront conversation strings, shared by templates and the browser."""

_STRINGS = {
    "title": ("AI yordamchi", "AI ёрдамчи", "AI-помощник"),
    "intro": (
        "Mahsulot haqida so'rang yoki qurilish mollari ro'yxatini yuboring.",
        "Маҳсулот ҳақида сўранг ёки қурилиш моллари рўйхатини юборинг.",
        "Задайте вопрос о товаре или отправьте список стройматериалов.",
    ),
    "open": ("Suhbatni ochish", "Суҳбатни очиш", "Открыть чат"),
    "history": ("Suhbat xabarlari", "Суҳбат хабарлари", "Сообщения чата"),
    "empty": (
        "Hali xabar yo'q. Savolingizni yozing.",
        "Ҳали хабар йўқ. Саволингизни ёзинг.",
        "Сообщений пока нет. Напишите свой вопрос.",
    ),
    "message": ("Xabaringiz", "Хабарингиз", "Ваше сообщение"),
    "placeholder": ("Xabar yozing…", "Хабар ёзинг…", "Напишите сообщение…"),
    "menu": ("Suhbat menyusi", "Суҳбат менюси", "Меню чата"),
    "send": ("Yuborish", "Юбориш", "Отправить"),
    "loading": ("Xabarlar yuklanmoqda…", "Хабарлар юкланмоқда…", "Загрузка сообщений…"),
    "sending": ("Xabar yuborilmoqda…", "Хабар юборилмоқда…", "Отправка сообщения…"),
    "pending": ("Javob kutilmoqda…", "Жавоб кутилмоқда…", "Ожидание ответа…"),
    "failed": (
        "So'rov bajarilmadi. Qayta urinishingiz mumkin.",
        "Сўров бажарилмади. Қайта уринишингиз мумкин.",
        "Запрос не выполнен. Можно повторить попытку.",
    ),
    "connection": (
        "Ulanish uzildi. Xabarlar yana tekshiriladi.",
        "Уланиш узилди. Хабарлар яна текширилади.",
        "Связь прервана. Проверка сообщений будет повторена.",
    ),
    "retry": ("Qayta urinish", "Қайта уриниш", "Повторить"),
    "request": ("So'rov", "Сўров", "Запрос"),
    "operator": ("Operatorni chaqirish", "Операторни чақириш", "Позвать оператора"),
    "ai": ("AI yordamchi bilan suhbat", "AI ёрдамчи билан суҳбат", "Чат с AI-помощником"),
    "requested": (
        "Operator so'raldi. Ulanishi kutilmoqda.",
        "Оператор сўралди. Уланиши кутилмоқда.",
        "Оператор запрошен. Ожидаем подключения.",
    ),
    "assigned": (
        "Suhbat operatorga biriktirilgan.",
        "Суҳбат операторга бириктирилган.",
        "Чат передан оператору.",
    ),
    "you": ("Siz", "Сиз", "Вы"),
    "assistant": ("AI yordamchi", "AI ёрдамчи", "AI-помощник"),
    "operator_name": ("Operator", "Оператор", "Оператор"),
    "system": ("QurBot", "QurBot", "QurBot"),
    "qty": ("Miqdor", "Миқдор", "Количество"),
    "add": ("Savatga qo'shish", "Саватга қўшиш", "Добавить в корзину"),
    "added": ("Savat yangilandi.", "Сават янгиланди.", "Корзина обновлена."),
    "cart_error": (
        "Savatni yangilab bo'lmadi. Miqdorni tekshirib, qayta urining.",
        "Саватни янгилаб бўлмади. Миқдорни текшириб, қайта урининг.",
        "Не удалось обновить корзину. Проверьте количество и повторите.",
    ),
    "cart_conflict": (
        "Savat boshqa joyda o'zgardi. Miqdorni tekshirib, qayta qo'shing.",
        "Сават бошқа жойда ўзгарди. Миқдорни текшириб, қайта қўшинг.",
        "Корзина изменена в другом окне. Проверьте количество и добавьте снова.",
    ),
    "unit_conflict": (
        "Savatdagi mahsulot birligi boshqacha. Miqdorni savatda tahrirlang.",
        "Саватдаги маҳсулот бирлиги бошқача. Миқдорни саватда таҳрирланг.",
        "Товар в корзине указан в другой единице. Измените количество в корзине.",
    ),
    "login": (
        "Suhbat uchun hisobingizga kiring.",
        "Суҳбат учун ҳисобингизга киринг.",
        "Войдите в аккаунт, чтобы открыть чат.",
    ),
    "session": (
        "Seans tugadi. Sahifani yangilang yoki qayta kiring.",
        "Сеанс тугади. Саҳифани янгиланг ёки қайта киринг.",
        "Сеанс завершён. Обновите страницу или войдите снова.",
    ),
    "no_js": (
        "Suhbat uchun brauzerda JavaScript yoqilgan bo'lishi kerak.",
        "Суҳбат учун браузерда JavaScript ёқилган бўлиши керак.",
        "Для чата включите JavaScript в браузере.",
    ),
    "hint": (
        "Yuborish tugmasi xabarni jo'natadi. Enter yangi qator ochadi.",
        "Юбориш тугмаси хабарни жўнатади. Enter янги қатор очади.",
        "Кнопка отправляет сообщение. Enter добавляет новую строку.",
    ),
}

CHAT_MESSAGES: dict[str, dict[str, str]] = {
    f"web_chat_{key}": dict(zip(("uz_latn", "uz_cyrl", "ru"), values, strict=True))
    for key, values in _STRINGS.items()
}

CHAT_MESSAGES.update(
    {
        "chat_choose_quantity": {
            "uz_latn": "Savatga qo'shish uchun miqdorni tanlang:",
            "uz_cyrl": "Саватга қўшиш учун миқдорни танланг:",
            "ru": "Выберите количество для добавления в корзину:",
        },
        "web_product_confirm_required": {
            "uz_latn": "Narx va mavjudlik operator tomonidan tasdiqlanadi",
            "uz_cyrl": "Нарх ва мавжудлик оператор томонидан тасдиқланади",
            "ru": "Цену и наличие должен подтвердить оператор",
        },
        "web_product_confirm_hint": {
            "uz_latn": "Narx yoki zaxira tasdiqlanmagan. Suhbatda operatorga murojaat qiling.",
            "uz_cyrl": "Нарх ёки захира тасдиқланмаган. Суҳбатда операторга мурожаат қилинг.",
            "ru": "Цена или остаток не подтверждены. Обратитесь к оператору в чате.",
        },
        "chat_waiting": CHAT_MESSAGES["web_chat_requested"],
        "chat_queued": {
            "uz_latn": "Xabaringiz qabul qilindi. Javob kutilmoqda.",
            "uz_cyrl": "Хабарингиз қабул қилинди. Жавоб кутилмоқда.",
            "ru": "Сообщение принято. Ожидаем ответа.",
        },
        "chat_claim": {
            "uz_latn": "Suhbatni qabul qilish",
            "uz_cyrl": "Суҳбатни қабул қилиш",
            "ru": "Принять чат",
        },
        "chat_close": {
            "uz_latn": "Suhbatni yakunlash",
            "uz_cyrl": "Суҳбатни якунлаш",
            "ru": "Завершить чат",
        },
        "chat_claimed": {
            "uz_latn": "Suhbat sizga biriktirildi.",
            "uz_cyrl": "Суҳбат сизга бириктирилди.",
            "ru": "Чат назначен вам.",
        },
        "chat_claim_conflict": {
            "uz_latn": "Amal bajarilmadi. Suhbat holati va huquqlaringizni tekshiring.",
            "uz_cyrl": "Амал бажарилмади. Суҳбат ҳолати ва ҳуқуқларингизни текширинг.",
            "ru": "Действие не выполнено. Проверьте состояние чата и ваши права.",
        },
        "chat_reply_sent": {
            "uz_latn": "Javob suhbatga qo'shildi.",
            "uz_cyrl": "Жавоб суҳбатга қўшилди.",
            "ru": "Ответ добавлен в чат.",
        },
        "chat_closed": {
            "uz_latn": (
                "Operator bilan suhbat yakunlandi. AI yordamchi bilan davom etishingiz mumkin."
            ),
            "uz_cyrl": "Оператор билан суҳбат якунланди. AI ёрдамчи билан давом этишингиз мумкин.",
            "ru": "Чат с оператором завершён. Можно продолжить с AI-помощником.",
        },
        "chat_ai_unavailable": {
            "uz_latn": "AI javob bera olmadi. Keyinroq yozing yoki operatorni chaqiring.",
            "uz_cyrl": "AI жавоб бера олмади. Кейинроқ ёзинг ёки операторни чақиринг.",
            "ru": "AI не смог ответить. Напишите позже или позовите оператора.",
        },
    }
)

CHAT_MESSAGES["web_chat_confirmation"] = CHAT_MESSAGES["web_product_confirm_required"]

CHAT_MESSAGES.update(
    {
        "web_auth_reopen": {
            "uz_latn": (
                "Telegram orqali kirish ishlamasa, eski tugmadan ochilgan ilovani yoping. "
                "Botga /webapp yuboring va yangi xabar ostidagi tugma orqali saytni qayta "
                "oching. Eski klaviatura tugmasidan foydalanmang."
            ),
            "uz_cyrl": (
                "Telegram орқали кириш ишламаса, эски тугмадан очилган иловани ёпинг. "
                "Ботга /webapp юборинг ва янги хабар остидаги тугма орқали сайтни қайта "
                "очинг. Эски клавиатура тугмасидан фойдаланманг."
            ),
            "ru": (
                "Если вход через Telegram не работает, закройте приложение, открытое старой "
                "кнопкой. Отправьте боту /webapp и откройте сайт кнопкой под новым "
                "сообщением. Не используйте старую кнопку клавиатуры."
            ),
        },
        "web_auth_recovery": {
            "uz_latn": (
                "Kirishni yakunlab bo'lmadi. Cookie va sayt xotirasiga ruxsat bering. "
                "Ilovani yoping, botga /webapp yuboring va yangi xabar ostidagi tugma "
                "orqali qayta oching."
            ),
            "uz_cyrl": (
                "Киришни якунлаб бўлмади. Cookie ва сайт хотирасига рухсат беринг. "
                "Иловани ёпинг, ботга /webapp юборинг ва янги хабар остидаги тугма "
                "орқали қайта очинг."
            ),
            "ru": (
                "Не удалось завершить вход. Разрешите cookie и хранилище сайта. Закройте "
                "приложение, отправьте боту /webapp и откройте его кнопкой под новым "
                "сообщением."
            ),
        },
        "web_auth_signing_in": {
            "uz_latn": "Telegram orqali kirish tekshirilmoqda…",
            "uz_cyrl": "Telegram орқали кириш текширилмоқда…",
            "ru": "Проверяем вход через Telegram…",
        },
    }
)
