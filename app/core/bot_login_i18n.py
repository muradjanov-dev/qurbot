"""Copy for the browser-bound Telegram confirmation login flow."""

BOT_LOGIN_MESSAGES: dict[str, dict[str, str]] = {
    "bot_login_other_methods": {
        "uz_latn": "Boshqa usulda kirish",
        "uz_cyrl": "Бошқа усулда кириш",
        "ru": "Другие способы входа",
    },
    "bot_login_title": {
        "uz_latn": "Telegram orqali hisobingizga kiring",
        "uz_cyrl": "Telegram орқали ҳисобингизга киринг",
        "ru": "Войдите в аккаунт через Telegram",
    },
    "bot_login_body": {
        "uz_latn": (
            "So‘rovni shu brauzerdan boshlang, Telegramda o‘zingiz " "tasdiqlang va qayting."
        ),
        "uz_cyrl": ("Сўровни шу браузердан бошланг, Telegramда ўзингиз " "тасдиқланг ва қайтинг."),
        "ru": "Начните запрос в этом браузере, подтвердите его в Telegram и вернитесь сюда.",
    },
    "bot_login_start": {
        "uz_latn": "Telegram orqali boshlash",
        "uz_cyrl": "Telegram орқали бошлаш",
        "ru": "Продолжить через Telegram",
    },
    "bot_login_start_hint": {
        "uz_latn": "Telegramda so‘rovni tasdiqlang, keyin shu brauzerga qayting.",
        "uz_cyrl": "Telegramда сўровни тасдиқланг, кейин шу браузерга қайтинг.",
        "ru": "Подтвердите запрос в Telegram, затем вернитесь в этот браузер.",
    },
    "bot_login_opening": {
        "uz_latn": "Telegram ochilmoqda…",
        "uz_cyrl": "Telegram очилмоқда…",
        "ru": "Открываем Telegram…",
    },
    "bot_login_code_label": {
        "uz_latn": "Tasdiqlash kodi",
        "uz_cyrl": "Тасдиқлаш коди",
        "ru": "Код подтверждения",
    },
    "bot_login_browser": {
        "uz_latn": "ushbu brauzer",
        "uz_cyrl": "шу браузер",
        "ru": "этот браузер",
    },
    "bot_login_expires": {
        "uz_latn": "Kod amal qilish muddati",
        "uz_cyrl": "Коднинг амал қилиш муддати",
        "ru": "Код действителен ещё",
    },
    "bot_login_waiting": {
        "uz_latn": "Telegramdagi tasdiqni kutyapmiz. Tasdiqlaganingizdan keyin shu oynaga qayting.",
        "uz_cyrl": "Telegramдаги тасдиқни кутяпмиз. Тасдиқлагандан кейин шу ойнага қайтинг.",
        "ru": "Ждём подтверждения в Telegram. После подтверждения вернитесь в это окно.",
    },
    "bot_login_approved": {
        "uz_latn": "Tasdiqlandi. Hisobingizga kiritamiz…",
        "uz_cyrl": "Тасдиқланди. Ҳисобингизга киритяпмиз…",
        "ru": "Подтверждено. Выполняем вход…",
    },
    "bot_login_denied": {
        "uz_latn": "So‘rov rad etildi. Yangi kod bilan qayta boshlashingiz mumkin.",
        "uz_cyrl": "Сўров рад этилди. Янги код билан қайта бошлашингиз мумкин.",
        "ru": "Запрос отклонён. Можно начать заново и получить новый код.",
    },
    "bot_login_expired": {
        "uz_latn": "Kod muddati tugadi. Qayta boshlang.",
        "uz_cyrl": "Код муддати тугади. Қайта бошланг.",
        "ru": "Срок действия кода истёк. Начните заново.",
    },
    "bot_login_unavailable": {
        "uz_latn": (
            "Hozir Telegram bilan ulanishni boshlay olmadik. "
            "Aloqani tekshirib, qayta urinib ko‘ring."
        ),
        "uz_cyrl": (
            "Ҳозир Telegram билан уланишни бошлай олмадик. "
            "Алоқани текшириб, қайта уриниб кўринг."
        ),
        "ru": "Не удалось начать вход через Telegram. Проверьте соединение и попробуйте ещё раз.",
    },
    "bot_login_retry": {
        "uz_latn": "Qayta boshlash",
        "uz_cyrl": "Қайта бошлаш",
        "ru": "Начать заново",
    },
    "bot_login_confirm": {
        "uz_latn": "Tasdiqlash",
        "uz_cyrl": "Тасдиқлаш",
        "ru": "Подтвердить",
    },
    "bot_login_cancel": {
        "uz_latn": "Bekor qilish",
        "uz_cyrl": "Бекор қилиш",
        "ru": "Отменить",
    },
    "bot_login_mismatch": {
        "uz_latn": "Telegramda ko‘rsatilgan kod mos kelmadi. Yangi so‘rov boshlang.",
        "uz_cyrl": "Telegramда кўрсатилган код мос келмади. Янги сўров бошланг.",
        "ru": "Код в Telegram не совпал. Начните новый запрос.",
    },
    "bot_login_return_browser": {
        "uz_latn": "Telegramda tasdiqlang, so‘ng shu brauzerga qayting.",
        "uz_cyrl": "Telegramда тасдиқланг, сўнг шу браузерга қайтинг.",
        "ru": "Подтвердите в Telegram, затем вернитесь в этот браузер.",
    },
    "bot_login_bot_prompt": {
        "uz_latn": (
            "Agar so‘rovni {browser}dagi {site} sahifasidan o‘zingiz boshlagan "
            "bo‘lsangiz va kod {code} bilan bir xil bo‘lsa, Telegramda tasdiqlang. "
        ),
        "uz_cyrl": (
            "Агар сўровни {browser}даги {site} саҳифасидан ўзингиз бошлаган "
            "бўлсангиз ва код {code} билан бир хил бўлса, Telegramда тасдиқланг. "
        ),
        "ru": (
            "Подтвердите запрос в Telegram, только если вы сами начали его "
            "на странице {site} в {browser} и видите тот же код {code}. "
        ),
    },
    "bot_login_bot_approved": {
        "uz_latn": "Kirish tasdiqlandi. Sayt ochiq turgan brauzer oynasiga qayting.",
        "uz_cyrl": "Кириш тасдиқланди. Сайт очиқ турган браузер ойнасига қайтинг.",
        "ru": "Вход подтверждён. Вернитесь в этот браузер, чтобы продолжить.",
    },
    "bot_login_bot_denied": {
        "uz_latn": "Kirish so‘rovi bekor qilindi. Hech kim hisobingizga kirmadi.",
        "uz_cyrl": "Кириш сўрови бекор қилинди. Ҳисобингизга ҳеч ким кирмади.",
        "ru": "Запрос на вход отклонён. Никто не вошёл в ваш аккаунт.",
    },
    "bot_login_invalid": {
        "uz_latn": "Faol kirish so‘rovi topilmadi. Brauzerda yangi kod so‘rang.",
        "uz_cyrl": "Фаол кириш сўрови топилмади. Браузерда янги код сўранг.",
        "ru": "Активный запрос на вход не найден. Запросите новый код в браузере.",
    },
    "bot_login_signed_in": {
        "uz_latn": "Hisobingizga kirdingiz.",
        "uz_cyrl": "Ҳисобингизга кирдингиз.",
        "ru": "Вы вошли в аккаунт.",
    },
    "bot_login_manual_check": {
        "uz_latn": "Holatni tekshirish",
        "uz_cyrl": "Ҳолатни текшириш",
        "ru": "Проверить статус",
    },
}
