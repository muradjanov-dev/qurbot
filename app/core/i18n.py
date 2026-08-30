"""Internationalization (i18n) module for QurBot.

Supports:
- uz_latn: O'zbekcha (Lotin) [Default]
- uz_cyrl: Ўзбекча (Кирилл)
- ru: Русский
"""

from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    # Onboarding & Language
    "choose_language": {
        "uz_latn": "Assalomu alaykum! QurBot ga xush kelibsiz. Iltimos, tilni tanlang:",
        "uz_cyrl": "Ассалому алайкум! QurBot га хуш келибсиз. Илтимос, тилни танланг:",
        "ru": "Здравствуйте! Добро пожаловать в QurBot. Пожалуйста, выберите язык:",
    },
    "choose_district": {
        "uz_latn": "Yetkazib berish tumanini tanlang:",
        "uz_cyrl": "Етказиб бериш туманини танланг:",
        "ru": "Выберите район доставки:",
    },
    "request_phone": {
        "uz_latn": (
            "Buyurtmalarni tasdiqlash uchun telefon raqamingizni yuboring "
            "(yoki o'tkazib yuboring):"
        ),
        "uz_cyrl": (
            "Буюртмаларни тасдиқлаш учун телефон рақамингизни юборинг " "(ёки ўтказиб юборинг):"
        ),
        "ru": ("Для подтверждения заказов отправьте номер телефона " "(или можете пропустить):"),
    },
    "btn_send_contact": {
        "uz_latn": "📱 Raqamni yuborish",
        "uz_cyrl": "📱 Рақамни юбориш",
        "ru": "📱 Отправить номер",
    },
    "btn_skip": {
        "uz_latn": "⏭ O'tkazib yuborish",
        "uz_cyrl": "⏭ Ўтказиб юбориш",
        "ru": "⏭ Пропустить",
    },
    "welcome_done": {
        "uz_latn": (
            "Xush kelibsiz! Endi siz qurilish materiallari ro'yxatini erkin matn "
            "shaklida yuborishingiz mumkin. Masalan:\n\n"
            "«<b>10 dona fanera 12mm, 5 dona osb 9mm, 20 dona dvp 3.2</b>»\n\n"
            "Qurilish mollaringizni ro'yxatini yuboring va biz Sizga ularni "
            "topib, jamlab, yetkazib beramiz."
        ),
        "uz_cyrl": (
            "Хуш келибсиз! Энди сиз қурилиш материаллари рўйхатини эркин матн "
            "шаклида юборишингиз мумкин. Масалан:\n\n"
            "«<b>10 дона фанера 12мм, 5 дона осб 9мм, 20 дона двп 3.2</b>»\n\n"
            "Қурилиш молларингизни рўйхатини юборинг ва биз Сизга уларни "
            "топиб, жамлаб, етказиб берамиз."
        ),
        "ru": (
            "Добро пожаловать! Теперь вы можете отправить список стройматериалов "
            "простым текстом. Например:\n\n"
            "«<b>10 шт фанера 12мм, 5 шт осб 9мм, 20 шт двп 3.2</b>»\n\n"
            "Отправьте список стройматериалов, а мы найдём их, "
            "соберём и доставим вам."
        ),
    },
    # ── Location & saved addresses ────────────────────────────────────────
    "request_location": {
        "uz_latn": (
            "📍 Yetkazib berish manzilingizni yuboring.\n\n"
            "Pastdagi tugmani bosing — biz manzilni o'zimiz aniqlab, "
            "sizga tasdiqlash uchun ko'rsatamiz."
        ),
        "uz_cyrl": (
            "📍 Етказиб бериш манзилингизни юборинг.\n\n"
            "Пастдаги тугмани босинг — биз манзилни ўзимиз аниқлаб, "
            "сизга тасдиқлаш учун кўрсатамиз."
        ),
        "ru": (
            "📍 Отправьте адрес доставки.\n\n"
            "Нажмите кнопку ниже — мы определим адрес сами "
            "и покажем вам на подтверждение."
        ),
    },
    "btn_send_location": {
        "uz_latn": "📍 Lokatsiyani yuborish",
        "uz_cyrl": "📍 Локацияни юбориш",
        "ru": "📍 Отправить локацию",
    },
    "btn_choose_district_instead": {
        "uz_latn": "🗺 Tumanni qo'lda tanlash",
        "uz_cyrl": "🗺 Туманни қўлда танлаш",
        "ru": "🗺 Выбрать район вручную",
    },
    "address_detected": {
        "uz_latn": (
            "📍 Manzilingiz shundaymi?\n\n<b>{address}</b>\n\n"
            "Agar noto'g'ri bo'lsa, tahrirlab yozing."
        ),
        "uz_cyrl": (
            "📍 Манзилингиз шундайми?\n\n<b>{address}</b>\n\n"
            "Агар нотўғри бўлса, таҳрирлаб ёзинг."
        ),
        "ru": ("📍 Ваш адрес такой?\n\n<b>{address}</b>\n\n" "Если неверно — отредактируйте."),
    },
    "address_not_detected": {
        "uz_latn": (
            "Lokatsiyani oldik, lekin manzil nomini aniqlay olmadik.\n"
            "Manzilni o'zingiz yozib yuboring (ko'cha, uy, mo'ljal):"
        ),
        "uz_cyrl": (
            "Локацияни олдик, лекин манзил номини аниқлай олмадик.\n"
            "Манзилни ўзингиз ёзиб юборинг (кўча, уй, мўлжал):"
        ),
        "ru": (
            "Локацию получили, но название адреса определить не удалось.\n"
            "Напишите адрес сами (улица, дом, ориентир):"
        ),
    },
    "address_ask_text": {
        "uz_latn": "Manzilni yozing (ko'cha, uy, mo'ljal):",
        "uz_cyrl": "Манзилни ёзинг (кўча, уй, мўлжал):",
        "ru": "Напишите адрес (улица, дом, ориентир):",
    },
    "address_saved": {
        "uz_latn": "✅ Manzil saqlandi:\n<b>{address}</b>",
        "uz_cyrl": "✅ Манзил сақланди:\n<b>{address}</b>",
        "ru": "✅ Адрес сохранён:\n<b>{address}</b>",
    },
    "address_outside_service_area": {
        "uz_latn": (
            "⚠️ Bu manzil hozircha bizning yetkazib berish hududimizdan tashqarida. "
            "Buyurtma berishingiz mumkin, lekin yetkazish shartlari alohida kelishiladi."
        ),
        "uz_cyrl": (
            "⚠️ Бу манзил ҳозирча бизнинг етказиб бериш ҳудудимиздан ташқарида. "
            "Буюртма беришингиз мумкин, лекин етказиш шартлари алоҳида келишилади."
        ),
        "ru": (
            "⚠️ Этот адрес пока вне нашей зоны доставки. "
            "Заказ оформить можно, но условия доставки обсуждаются отдельно."
        ),
    },
    "checkout_choose_address": {
        "uz_latn": "📍 Qayerga yetkazib beramiz?",
        "uz_cyrl": "📍 Қаерга етказиб берамиз?",
        "ru": "📍 Куда доставляем?",
    },
    "btn_new_address": {
        "uz_latn": "➕ Yangi manzil",
        "uz_cyrl": "➕ Янги манзил",
        "ru": "➕ Новый адрес",
    },
    "btn_address_confirm": {
        "uz_latn": "✅ To'g'ri",
        "uz_cyrl": "✅ Тўғри",
        "ru": "✅ Верно",
    },
    "btn_address_edit": {
        "uz_latn": "✏️ Tahrirlash",
        "uz_cyrl": "✏️ Таҳрирлаш",
        "ru": "✏️ Изменить",
    },
    "menu_my_addresses": {
        "uz_latn": "📍 Manzillarim",
        "uz_cyrl": "📍 Манзилларим",
        "ru": "📍 Мои адреса",
    },
    "addresses_empty": {
        "uz_latn": "Sizda saqlangan manzil yo'q.",
        "uz_cyrl": "Сизда сақланган манзил йўқ.",
        "ru": "У вас нет сохранённых адресов.",
    },
    # Main Menu
    "menu_send_list": {
        "uz_latn": "🧾 Ro'yxat yuborish",
        "uz_cyrl": "🧾 Рўйхат юбориш",
        "ru": "🧾 Отправить список",
    },
    "menu_my_orders": {
        "uz_latn": "📦 Buyurtmalarim",
        "uz_cyrl": "📦 Буюртмаларим",
        "ru": "📦 Мои заказы",
    },
    "language_changed": {
        "uz_latn": "✅ Til o'zgartirildi.",
        "uz_cyrl": "✅ Тил ўзгартирилди.",
        "ru": "✅ Язык изменён.",
    },
    "menu_cabinet": {
        "uz_latn": "👤 Kabinet",
        "uz_cyrl": "👤 Кабинет",
        "ru": "👤 Кабинет",
    },
    "pebbles_earned": {
        "uz_latn": "🪨 Siz <b>{pebbles} toshcha</b> yutdingiz!",
        "uz_cyrl": "🪨 Сиз <b>{pebbles} тошча</b> ютдингиз!",
        "ru": "🪨 Вы получили <b>{pebbles} камешков</b>!",
    },
    "pebbles_balance": {
        "uz_latn": "🪨 Toshchalaringiz: <b>{pebbles}</b>",
        "uz_cyrl": "🪨 Тошчаларингиз: <b>{pebbles}</b>",
        "ru": "🪨 Ваши камешки: <b>{pebbles}</b>",
    },
    "cabinet_title": {
        "uz_latn": "👤 <b>Kabinet</b>\n\nQuyidagilardan birini tanlang:",
        "uz_cyrl": "👤 <b>Кабинет</b>\n\nҚуйидагилардан бирини танланг:",
        "ru": "👤 <b>Кабинет</b>\n\nВыберите один из пунктов:",
    },
    "btn_main_menu": {
        "uz_latn": "⬅️ Asosiy menyu",
        "uz_cyrl": "⬅️ Асосий меню",
        "ru": "⬅️ Главное меню",
    },
    "menu_price_check": {
        "uz_latn": "🛒 Mahsulotlar va narxlar",
        "uz_cyrl": "🛒 Маҳсулотлар ва нархлар",
        "ru": "🛒 Товары и цены",
    },
    # Customer-facing product view. The supplier count is deliberately absent:
    # to the customer this is one catalogue, not a list of vendors bidding.
    "product_card": {
        "uz_latn": (
            "<b>{name}</b>\n\n"
            "🏷 Brend: {brand}\n"
            "💰 Narx: <b>{min_price} — {max_price} so'm</b>\n"
            "📏 O'lchov: {unit}"
        ),
        "uz_cyrl": (
            "<b>{name}</b>\n\n"
            "🏷 Бренд: {brand}\n"
            "💰 Нарх: <b>{min_price} — {max_price} сўм</b>\n"
            "📏 Ўлчов: {unit}"
        ),
        "ru": (
            "<b>{name}</b>\n\n"
            "🏷 Бренд: {brand}\n"
            "💰 Цена: <b>{min_price} — {max_price} сум</b>\n"
            "📏 Единица: {unit}"
        ),
    },
    # "Not available" on its own is where the customer leaves. The apology and
    # a number to call turn a dead end into a phone order -- which is how this
    # trade already works, and how an older customer prefers to be served.
    "product_card_no_offers": {
        "uz_latn": (
            "<b>{name}</b>\n\n"
            "Kechirasiz, bu mahsulot hozircha tugagan 😔\n"
            "Iltimos, qo'ng'iroq qilib so'rang: <b>{phone}</b>"
        ),
        "uz_cyrl": (
            "<b>{name}</b>\n\n"
            "Кечирасиз, бу маҳсулот ҳозирча тугаган 😔\n"
            "Илтимос, қўнғироқ қилиб сўранг: <b>{phone}</b>"
        ),
        "ru": (
            "<b>{name}</b>\n\n"
            "Извините, этого товара сейчас нет 😔\n"
            "Пожалуйста, позвоните и уточните: <b>{phone}</b>"
        ),
    },
    "price_browse_choose_category": {
        "uz_latn": "🔍 <b>Mahsulot narxlari</b>\n\nKategoriyani tanlang:",
        "uz_cyrl": "🔍 <b>Маҳсулот нархлари</b>\n\nКатегорияни танланг:",
        "ru": "🔍 <b>Цены на товары</b>\n\nВыберите категорию:",
    },
    "price_browse_empty": {
        "uz_latn": (
            "Bu kategoriyada hozircha narxlar yo'q 😔\n"
            "Kerakli mahsulotni telefon orqali so'rang: <b>{phone}</b>"
        ),
        "uz_cyrl": (
            "Бу категорияда ҳозирча нархлар йўқ 😔\n"
            "Керакли маҳсулотни телефон орқали сўранг: <b>{phone}</b>"
        ),
        "ru": (
            "В этой категории пока нет цен 😔\n" "Спросите нужный товар по телефону: <b>{phone}</b>"
        ),
    },
    "price_browse_header": {
        "uz_latn": "💰 <b>{category}</b>\n\nBatafsil ko'rish uchun mahsulotni tanlang:",
        "uz_cyrl": "💰 <b>{category}</b>\n\nБатафсил кўриш учун маҳсулотни танланг:",
        "ru": "💰 <b>{category}</b>\n\nВыберите товар, чтобы посмотреть подробнее:",
    },
    "price_browse_hint": {
        "uz_latn": "\n<i>Narxlar — biz taklif qilayotgan eng arzon narx.</i>",
        "uz_cyrl": "\n<i>Нархлар — биз таклиф қилаётган энг арзон нарх.</i>",
        "ru": "\n<i>Цены — наше лучшее предложение.</i>",
    },
    "menu_shop_portal": {
        "uz_latn": "🏪 Do'kon paneli",
        "uz_cyrl": "🏪 Дўкон панели",
        "ru": "🏪 Панель магазина",
    },
    "menu_settings": {
        "uz_latn": "⚙️ Sozlamalar",
        "uz_cyrl": "⚙️ Созламалар",
        "ru": "⚙️ Настройки",
    },
    "settings_menu": {
        "uz_latn": "⚙️ <b>Sozlamalar</b>\n\nKerakli bo'limni tanlang:",
        "uz_cyrl": "⚙️ <b>Созламалар</b>\n\nКеракли бўлимни танланг:",
        "ru": "⚙️ <b>Настройки</b>\n\nВыберите нужный раздел:",
    },
    "btn_change_language": {
        "uz_latn": "🌐 Tilni o'zgartirish",
        "uz_cyrl": "🌐 Тилни ўзгартириш",
        "ru": "🌐 Изменить язык",
    },
    "btn_reregister": {
        "uz_latn": "🔄 0 dan qayta ro'yxatdan o'tish",
        "uz_cyrl": "🔄 0 дан қайта рўйхатдан ўтиш",
        "ru": "🔄 Перерегистрация (с нуля)",
    },
    "reregister_confirm_prompt": {
        "uz_latn": (
            "⚠️ <b>0 dan qayta ro'yxatdan o'tish</b>\n\n"
            "Barcha ma'lumotlaringiz (til, tuman va saqlangan manzillar) tozalanadi va "
            "boshidan qayta kiritiladi.\n\n"
            "Haqiqatan ham qayta ro'yxatdan o'tishni istaysizmi?"
        ),
        "uz_cyrl": (
            "⚠️ <b>0 дан қайта рўйхатдан ўтиш</b>\n\n"
            "Барча маълумотларингиз (тил, туман ва сақланган манзиллар) тозаланади ва "
            "бошидан қайта киритилади.\n\n"
            "Ҳақиқатан ҳам қайта рўйхатдан ўтишни истайсизми?"
        ),
        "ru": (
            "⚠️ <b>Перерегистрация с нуля</b>\n\n"
            "Все ваши данные (язык, район и сохранённые адреса) будут очищены и "
            "введены заново с самого начала.\n\n"
            "Вы действительно хотите пройти регистрацию заново?"
        ),
    },
    "btn_confirm_reregister": {
        "uz_latn": "✅ Ha, qaytadan boshlash",
        "uz_cyrl": "✅ Ҳа, қайтадан бошлаш",
        "ru": "✅ Да, начать заново",
    },
    "btn_cancel_reregister": {
        "uz_latn": "❌ Bekor qilish",
        "uz_cyrl": "❌ Бекор қилиш",
        "ru": "❌ Отмена",
    },
    # The example is the instruction. Asking for a list and leaving the shape
    # to be guessed is what produced most "tushunmadim" replies, and the people
    # this bot is for do not experiment -- they close the chat. Same wording and
    # same three products as basket_not_understood, so a customer who gets it
    # wrong is shown exactly what they were shown before.
    "prompt_send_basket": {
        "uz_latn": (
            "Qurilish mollari ro'yxatini yuboring.\n"
            "Har bir mahsulotni yangi qatordan, <b>miqdor + birlik + nom</b> "
            "tartibida yozing. Masalan:\n\n"
            "10 dona fanera 12mm\n5 dona osb 9mm\n20 dona dvp 3.2"
        ),
        "uz_cyrl": (
            "Қурилиш моллари рўйхатини юборинг.\n"
            "Ҳар бир маҳсулотни янги қатордан, <b>миқдор + бирлик + ном</b> "
            "тартибида ёзинг. Масалан:\n\n"
            "10 дона фанера 12мм\n5 дона осб 9мм\n20 дона двп 3.2"
        ),
        "ru": (
            "Отправьте список стройматериалов.\n"
            "Пишите каждый товар с новой строки в формате "
            "<b>количество + единица + название</b>. Например:\n\n"
            "10 шт фанера 12мм\n5 шт осб 9мм\n20 шт двп 3.2"
        ),
    },
    "parsing_in_progress": {
        "uz_latn": "⏳ Ro'yxat tahlil qilinmoqda…",
        "uz_cyrl": "⏳ Рўйхат таҳлил қилинмоқда…",
        "ru": "⏳ Список анализируется…",
    },
    "basket_not_understood": {
        "uz_latn": (
            "Kechirasiz, tushunmadim 🙂\n"
            "QurBot qurilish mollari narxini hisoblaydi. Har bir mahsulotni "
            "yangi qatordan, <b>miqdor + birlik + nom</b> tartibida yozing. Masalan:\n\n"
            "10 dona fanera 12mm\n5 dona osb 9mm\n20 dona dvp 3.2"
        ),
        "uz_cyrl": (
            "Кечирасиз, тушунмадим 🙂\n"
            "QurBot қурилиш моллари нархини ҳисоблайди. Ҳар бир маҳсулотни "
            "янги қатордан, <b>миқдор + бирлик + ном</b> тартибида ёзинг. Масалан:\n\n"
            "10 дона фанера 12мм\n5 дона осб 9мм\n20 дона двп 3.2"
        ),
        "ru": (
            "Извините, не понял 🙂\n"
            "QurBot считает цены на стройматериалы. Пишите каждый товар с новой "
            "строки в формате <b>количество + единица + название</b>. Например:\n\n"
            "10 шт фанера 12мм\n5 шт осб 9мм\n20 шт двп 3.2"
        ),
    },
    "qty_out_of_range": {
        "uz_latn": "miqdor 1 dan 1 000 000 gacha bo'lishi kerak",
        "uz_cyrl": "миқдор 1 дан 1 000 000 гача бўлиши керак",
        "ru": "количество должно быть от 1 до 1 000 000",
    },
    "btn_add_to_basket": {
        "uz_latn": "🛒 Savatga qo'shish",
        "uz_cyrl": "🛒 Саватга қўшиш",
        "ru": "🛒 Добавить в корзину",
    },
    "price_ask_qty": {
        "uz_latn": (
            "<b>{name}</b>\n\n" "Nechta kerak? Faqat sonni yozing ({unit}):\n" "<i>Masalan: 10</i>"
        ),
        "uz_cyrl": (
            "<b>{name}</b>\n\n" "Нечта керак? Фақат сонни ёзинг ({unit}):\n" "<i>Масалан: 10</i>"
        ),
        "ru": (
            "<b>{name}</b>\n\n"
            "Сколько нужно? Напишите только число ({unit}):\n"
            "<i>Например: 10</i>"
        ),
    },
    "price_qty_not_a_number": {
        "uz_latn": "Faqat son yozing. Masalan: 10",
        "uz_cyrl": "Фақат сон ёзинг. Масалан: 10",
        "ru": "Напишите только число. Например: 10",
    },
    "price_added_to_basket": {
        "uz_latn": "✅ <b>{name}</b> savatga qo'shildi ({qty} {unit}).",
        "uz_cyrl": "✅ <b>{name}</b> саватга қўшилди ({qty} {unit}).",
        "ru": "✅ <b>{name}</b> добавлен в корзину ({qty} {unit}).",
    },
    "basket_parsed_header": {
        "uz_latn": "📋 <b>Ro'yxatingiz ({count} ta):</b>\n",
        "uz_cyrl": "📋 <b>Рўйхатингиз ({count} та):</b>\n",
        "ru": "📋 <b>Ваш список ({count} шт.):</b>\n",
    },
    "choose_candidate_prompt": {
        "uz_latn": "❓ <i>«{name}»</i> uchun aniq turini tanlang:",
        "uz_cyrl": "❓ <i>«{name}»</i> учун аниқ турини танланг:",
        "ru": "❓ Уточните, что вы имели в виду под <i>«{name}»</i>:",
    },
    # The question itself is written by the model in the customer's own
    # language, so all three variants carry the same frame -- only the name and
    # the question move.
    "clarify_question_prompt": {
        "uz_latn": "\u2753 <i>\u00ab{name}\u00bb</i> \u2014 {question}",
        "uz_cyrl": "\u2753 <i>\u00ab{name}\u00bb</i> \u2014 {question}",
        "ru": "\u2753 <i>\u00ab{name}\u00bb</i> \u2014 {question}",
    },
    "candidate_selected": {
        "uz_latn": "✅ Tanlandi: <b>{name}</b>",
        "uz_cyrl": "✅ Танланди: <b>{name}</b>",
        "ru": "✅ Выбрано: <b>{name}</b>",
    },
    "prompt_add_item": {
        "uz_latn": "Ro'yxatga qo'shmoqchi bo'lgan mahsulot(lar)ni yozing:",
        "uz_cyrl": "Рўйхатга қўшмоқчи бўлган маҳсулот(лар)ни ёзинг:",
        "ru": "Напишите товар(ы), которые хотите добавить в список:",
    },
    "prompt_edit_basket": {
        "uz_latn": (
            "Joriy ro'yxatingiz:\n{current_list}\n\n"
            "To'g'irlangan to'liq ro'yxatni qayta yuboring — u eskisining o'rnini bosadi:"
        ),
        "uz_cyrl": (
            "Жорий рўйхатингиз:\n{current_list}\n\n"
            "Тўғирланган тўлиқ рўйхатни қайта юборинг — у эскисининг ўрнини босади:"
        ),
        "ru": (
            "Ваш текущий список:\n{current_list}\n\n"
            "Отправьте исправленный полный список — он заменит старый:"
        ),
    },
    "btn_edit_basket": {
        "uz_latn": "✏️ Tahrirlash",
        "uz_cyrl": "✏️ Таҳрирлаш",
        "ru": "✏️ Редактировать",
    },
    "btn_add_item": {
        "uz_latn": "➕ Qo'shish",
        "uz_cyrl": "➕ Қўшиш",
        "ru": "➕ Добавить",
    },
    "btn_clear_basket": {
        "uz_latn": "🗑 O'chirish",
        "uz_cyrl": "🗑 Ўчириш",
        "ru": "🗑 Очистить",
    },
    "btn_calculate_quotes": {
        "uz_latn": "🔎 Buyurtma qilish",
        "uz_cyrl": "🔎 Буюртма қилиш",
        "ru": "🔎 Оформить заказ",
    },
    "btn_select_quote": {
        "uz_latn": "✅ Buyurtmani tasdiqlash",
        "uz_cyrl": "✅ Буюртмани тасдиқлаш",
        "ru": "✅ Подтвердить заказ",
    },
    "btn_get_pdf": {
        "uz_latn": "📄 PDF olish",
        "uz_cyrl": "📄 PDF олиш",
        "ru": "📄 Скачать PDF",
    },
    "pdf_generating": {
        "uz_latn": "📄 PDF tayyorlanmoqda...",
        "uz_cyrl": "📄 PDF тайёрланмоқда...",
        "ru": "📄 Готовим PDF...",
    },
    "quote_header_cheapest": {
        "uz_latn": "💰 <b>ENG TEJAMLI VARIANT</b>",
        "uz_cyrl": "💰 <b>ЭНГ ТЕЖАМЛИ ВАРИАНТ</b>",
        "ru": "💰 <b>САМЫЙ ВЫГОДНЫЙ ВАРИАНТ</b>",
    },
    # Named for what the customer gets, not for how it is sourced: a single
    # supplier means one delivery, and the supplier itself is never shown.
    "quote_header_single_shop": {
        "uz_latn": "📦 <b>BIR YETKAZIBDA</b>",
        "uz_cyrl": "📦 <b>БИР ЕТКАЗИБДА</b>",
        "ru": "📦 <b>ОДНОЙ ДОСТАВКОЙ</b>",
    },
    "quote_header_fastest": {
        "uz_latn": "⚡️ <b>ENG TEZ YETKAZIB BERISH</b>",
        "uz_cyrl": "⚡️ <b>ЭНГ ТЕЗ ЕТКАЗИБ БЕРИШ</b>",
        "ru": "⚡️ <b>САМАЯ БЫСТРАЯ ДОСТАВКА</b>",
    },
    "quote_header_premium": {
        "uz_latn": "⭐️ <b>PREMIUM BRENDLAR</b>",
        "uz_cyrl": "⭐️ <b>ПРЕМИУМ БРЕНДЛАР</b>",
        "ru": "⭐️ <b>ПРЕМИУМ БРЕНДЫ</b>",
    },
    "quote_header_balanced": {
        "uz_latn": "⚖️ <b>BALANSLASHGAN VARIANT</b>",
        "uz_cyrl": "⚖️ <b>БАЛАНСЛАШГАН ВАРИАНТ</b>",
        "ru": "⚖️ <b>СБАЛАНСИРОВАННЫЙ ВАРИАНТ</b>",
    },
    "quote_items_total": {
        "uz_latn": "Mahsulotlar:",
        "uz_cyrl": "Маҳсулотлар:",
        "ru": "Товары:",
    },
    "quote_delivery_total": {
        "uz_latn": "Dostavka:",
        "uz_cyrl": "Доставка:",
        "ru": "Доставка:",
    },
    "quote_grand_total": {
        "uz_latn": "JAMI:",
        "uz_cyrl": "ЖАМИ:",
        "ru": "ИТОГО:",
    },
    "quote_savings": {
        "uz_latn": "✅ {amount} so'm tejaysiz ({pct}%)",
        "uz_cyrl": "✅ {amount} сўм тежайсиз ({pct}%)",
        "ru": "✅ Вы экономите {amount} сум ({pct}%)",
    },
    "quote_coverage": {
        "uz_latn": "📦 Qamrov: {covered}/{total} mahsulot",
        "uz_cyrl": "📦 Қамров: {covered}/{total} маҳсулот",
        "ru": "📦 Найдено: {covered}/{total} товаров",
    },
    "quote_delivery_eta": {
        "uz_latn": "🚚 Yetkazish: {eta_min}-{eta_max} soat ichida",
        "uz_cyrl": "🚚 Етказиш: {eta_min}-{eta_max} соат ичида",
        "ru": "🚚 Доставка: в течение {eta_min}-{eta_max} ч.",
    },
    "prompt_checkout_address": {
        "uz_latn": "Iltimos, aniq yetkazib berish manzilini (ko'cha, uy/mo'ljal) yozing:",
        "uz_cyrl": "Илтимос, аниқ етказиб бериш манзилини (кўча, уй/мўлжал) ёзинг:",
        "ru": "Пожалуйста, укажите точный адрес доставки (улица, дом/ориентир):",
    },
    "prompt_checkout_phone": {
        "uz_latn": "Bog'lanish uchun telefon raqamingizni tasdiqlang (+998XXXXXXXXX):",
        "uz_cyrl": "Боғланиш учун телефон рақамингизни тасдиқланг (+998XXXXXXXXX):",
        "ru": "Подтвердите контактный номер телефона (+998XXXXXXXXX):",
    },
    "prompt_checkout_comment": {
        "uz_latn": (
            "Buyurtmaga qo'shimcha izoh yoki istak (ixtiyoriy, 'yo'q' deb yozishingiz mumkin):"
        ),
        "uz_cyrl": "Буюртмага қўшимча изоҳ ёки истак (ихтиёрий, 'йўқ' деб ёзишингиз мумкин):",
        "ru": "Комментарий к заказу (необязательно, можете написать 'нет'):",
    },
    "order_confirm_prompt": {
        "uz_latn": (
            "📝 <b>Buyurtmangizni tekshiring:</b>\n\n"
            "📞 Telefon: {phone}\n"
            "📍 Manzil: {address}\n"
            "💬 Izoh: {comment}\n"
        ),
        "uz_cyrl": (
            "📝 <b>Буюртмангизни текширинг:</b>\n\n"
            "📞 Телефон: {phone}\n"
            "📍 Манзил: {address}\n"
            "💬 Изоҳ: {comment}\n"
        ),
        "ru": (
            "📝 <b>Проверьте ваш заказ:</b>\n\n"
            "📞 Телефон: {phone}\n"
            "📍 Адрес: {address}\n"
            "💬 Комментарий: {comment}\n"
        ),
    },
    "order_confirm_question": {
        "uz_latn": "Barchasi to'g'rimi? Buyurtmani tasdiqlaysizmi?",
        "uz_cyrl": "Барчаси тўғрими? Буюртмани тасдиқлайсизми?",
        "ru": "Всё верно? Подтвердить заказ?",
    },
    "comment_none": {
        "uz_latn": "yo'q",
        "uz_cyrl": "йўқ",
        "ru": "нет",
    },
    "btn_confirm_order": {
        "uz_latn": "✅ Tasdiqlash",
        "uz_cyrl": "✅ Тасдиқлаш",
        "ru": "✅ Подтвердить",
    },
    "order_created_success": {
        "uz_latn": (
            "🎉 <b>Buyurtmangiz qabul qilindi!</b>\n\n"
            "Buyurtma raqami: <b>#{order_id}</b>\n"
            "Jami summa: <b>{total} so'm</b>\n\n"
            "Buyurtmangiz tayyorlanmoqda, tez orada siz bilan bog'lanamiz."
        ),
        "uz_cyrl": (
            "🎉 <b>Буюртмангиз қабул қилинди!</b>\n\n"
            "Буюртма рақами: <b>#{order_id}</b>\n"
            "Жами сумма: <b>{total} сўм</b>\n\n"
            "Буюртмангиз тайёрланмоқда, тез орада сиз билан боғланамиз."
        ),
        "ru": (
            "🎉 <b>Ваш заказ успешно оформлен!</b>\n\n"
            "Номер заказа: <b>#{order_id}</b>\n"
            "Сумма к оплате: <b>{total} сум</b>\n\n"
            "Ваш заказ собирается, мы скоро свяжемся с вами."
        ),
    },
    # Shop Owner Flow
    "shop_panel_title": {
        "uz_latn": "🏪 <b>Do'kon boshqaruv paneli</b>\n\nDo'kon: <b>{shop_name}</b>",
        "uz_cyrl": "🏪 <b>Дўкон бошқарув панели</b>\n\nДўкон: <b>{shop_name}</b>",
        "ru": "🏪 <b>Панель управления магазином</b>\n\nМагазин: <b>{shop_name}</b>",
    },
    "btn_quick_price": {
        "uz_latn": "✏️ Tez narx yangilash",
        "uz_cyrl": "✏️ Тез нарх янгилаш",
        "ru": "✏️ Быстрое обновление цены",
    },
    "btn_shop_products": {
        "uz_latn": "📊 Mahsulotlarim",
        "uz_cyrl": "📊 Маҳсулотларим",
        "ru": "📊 Мои товары",
    },
    "btn_shop_orders": {
        "uz_latn": "🔔 Yangi buyurtmalar",
        "uz_cyrl": "🔔 Янги буюртмалар",
        "ru": "🔔 Новые заказы",
    },
    "quick_price_prompt": {
        "uz_latn": (
            "Tez narx yangilash uchun mahsulot va narxni yuboring.\n"
            "Masalan: <code>fanera 12mm 157000</code> yoki <code>osb 9mm 118000</code>"
        ),
        "uz_cyrl": (
            "Тез нарх янгилаш учун маҳсулот ва нархни юборинг.\n"
            "Масалан: <code>фанера 12мм 157000</code> ёки <code>осб 9мм 118000</code>"
        ),
        "ru": (
            "Для быстрого обновления отправьте название и цену.\n"
            "Например: <code>фанера 12мм 157000</code> или <code>осб 9мм 118000</code>"
        ),
    },
    "price_updated_success": {
        "uz_latn": "✅ <b>{product_name}</b> narxi <b>{price} so'm</b> ga yangilandi!",
        "uz_cyrl": "✅ <b>{product_name}</b> нархи <b>{price} сўм</b> га янгиланди!",
        "ru": "✅ Цена товара <b>{product_name}</b> обновлена: <b>{price} сум</b>!",
    },
    # General & Errors
    "error_generic": {
        "uz_latn": "Kutilmagan xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
        "uz_cyrl": "Кутилмаган хатолик юз берди. Илтимос, кейинроқ қайта уриниб кўринг.",
        "ru": "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.",
    },
    "btn_back": {
        "uz_latn": "⬅️ Orqaga",
        "uz_cyrl": "⬅️ Орқага",
        "ru": "⬅️ Назад",
    },
    "btn_cancel": {
        "uz_latn": "❌ Bekor qilish",
        "uz_cyrl": "❌ Бекор қилиш",
        "ru": "❌ Отмена",
    },
    "action_cancelled": {
        "uz_latn": "Amal bekor qilindi.",
        "uz_cyrl": "Амал бекор қилинди.",
        "ru": "Действие отменено.",
    },
    # ─── Supplier / Import ─────────────────────────────────────────
    "upload_processing": {
        "uz_latn": "⏳ Fayl tahlil qilinmoqda...",
        "uz_cyrl": "⏳ Файл таҳлил қилинмоқда...",
        "ru": "⏳ Файл обрабатывается...",
    },
    "batch_summary": {
        "uz_latn": (
            "📊 <b>Import natijasi:</b>\n\n"
            "Jami qatorlar: {total}\n"
            "✅ Avtomatik moslashtirildi: {auto_count}\n"
            "⚠️ Tasdiqlash kutilmoqda: {manual_count}\n"
            "❌ O'tkazib yuborildi: {skipped}"
        ),
        "uz_cyrl": (
            "📊 <b>Импорт натижаси:</b>\n\n"
            "Жами қаторлар: {total}\n"
            "✅ Автоматик мослаштирилди: {auto_count}\n"
            "⚠️ Тасдиқлаш кутилмоқда: {manual_count}\n"
            "❌ Ўтказиб юборилди: {skipped}"
        ),
        "ru": (
            "📊 <b>Результат импорта:</b>\n\n"
            "Всего строк: {total}\n"
            "✅ Автоматически сопоставлено: {auto_count}\n"
            "⚠️ Ожидает подтверждения: {manual_count}\n"
            "❌ Пропущено: {skipped}"
        ),
    },
    "batch_applied": {
        "uz_latn": "✅ {count} ta mahsulot narxi muvaffaqiyatli yangilandi!",
        "uz_cyrl": "✅ {count} та маҳсулот нархи муваффақиятли янгиланди!",
        "ru": "✅ Цены на {count} товаров успешно обновлены!",
    },
    "batch_cancelled": {
        "uz_latn": "❌ Import bekor qilindi.",
        "uz_cyrl": "❌ Импорт бекор қилинди.",
        "ru": "❌ Импорт отменён.",
    },
    "import_row_resolved": {
        "uz_latn": "✅ «{name}» → {canonical_name} deb moslashtirildi.",
        "uz_cyrl": "✅ «{name}» → {canonical_name} деб мослаштирилди.",
        "ru": "✅ «{name}» → {canonical_name} сопоставлено.",
    },
    "btn_confirm_all": {
        "uz_latn": "✅ Barchasini tasdiqlash",
        "uz_cyrl": "✅ Барчасини тасдиқлаш",
        "ru": "✅ Подтвердить все",
    },
    "btn_review_unmatched": {
        "uz_latn": "📝 Tahrirlarni ko'rish",
        "uz_cyrl": "📝 Таҳрирларни кўриш",
        "ru": "📝 Просмотреть несовпадения",
    },
    "btn_cancel_import": {
        "uz_latn": "❌ Bekor qilish",
        "uz_cyrl": "❌ Бекор қилиш",
        "ru": "❌ Отменить",
    },
    "products_list_title": {
        "uz_latn": "📦 <b>Sizning mahsulotlaringiz</b> (Sahifa {page}/{total_pages}):",
        "uz_cyrl": "📦 <b>Сизнинг маҳсулотларингиз</b> (Саҳифа {page}/{total_pages}):",
        "ru": "📦 <b>Ваши товары</b> (Страница {page}/{total_pages}):",
    },
    "products_empty": {
        "uz_latn": "Sizda hali mahsulotlar mavjud emas.",
        "uz_cyrl": "Сизда ҳали маҳсулотлар мавжуд эмас.",
        "ru": "У вас пока нет товаров.",
    },
    "delivery_rules_title": {
        "uz_latn": (
            "🚚 <b>Yetkazish sozlamalari:</b>\n\n"
            "Yangilash uchun quyidagi formatda yozing:\n"
            "<code>dostavka [tuman] [narx] free:[summa] min:[summa]</code>"
        ),
        "uz_cyrl": (
            "🚚 <b>Етказиш созламалари:</b>\n\n"
            "Янгилаш учун қуйидаги форматда ёзинг:\n"
            "<code>dostavka [туман] [нарх] free:[сумма] min:[сумма]</code>"
        ),
        "ru": (
            "🚚 <b>Настройки доставки:</b>\n\n"
            "Для обновления напишите в формате:\n"
            "<code>доставка [район] [стоимость] free:[сумма] min:[сумма]</code>"
        ),
    },
    "delivery_rule_updated": {
        "uz_latn": "✅ {district} tumani uchun yetkazish sozlamalari yangilandi.",
        "uz_cyrl": "✅ {district} тумани учун етказиш созламалари янгиланди.",
        "ru": "✅ Настройки доставки для {district} обновлены.",
    },
    "upload_hint": {
        "uz_latn": (
            "📤 Narxlarni yuklash uchun Excel yoki CSV faylni yuboring.\n"
            "Fayl sarlavhalarida <b>Nomi</b> va <b>Narxi</b> ustunlari bo'lishi kerak."
        ),
        "uz_cyrl": (
            "📤 Нархларни юклаш учун Excel ёки CSV файлни юборинг.\n"
            "Файл сарлавҳаларида <b>Номи</b> ва <b>Нархи</b> устунлари бўлиши керак."
        ),
        "ru": (
            "📤 Для загрузки цен отправьте файл Excel или CSV.\n"
            "В заголовках файла должны быть столбцы <b>Наименование</b> и <b>Цена</b>."
        ),
    },
    "no_shop_found": {
        "uz_latn": "Sizga biriktirilgan do'kon topilmadi.",
        "uz_cyrl": "Сизга бириктирилган дўкон топилмади.",
        "ru": "Магазин, привязанный к вам, не найден.",
    },
    # ── Admin panel (in-bot, admins only) ─────────────────────────────────
    "menu_admin_panel": {
        "uz_latn": "🛠 Admin panel",
        "uz_cyrl": "🛠 Админ панел",
        "ru": "🛠 Админ-панель",
    },
    "adm_btn_stats": {
        "uz_latn": "📊 Statistika",
        "uz_cyrl": "📊 Статистика",
        "ru": "📊 Статистика",
    },
    "adm_btn_shops": {
        "uz_latn": "🏪 Do'konlar",
        "uz_cyrl": "🏪 Дўконлар",
        "ru": "🏪 Магазины",
    },
    "adm_btn_products": {
        "uz_latn": "📦 Mahsulotlar",
        "uz_cyrl": "📦 Маҳсулотлар",
        "ru": "📦 Товары",
    },
    "adm_btn_users": {
        "uz_latn": "👥 Foydalanuvchilar",
        "uz_cyrl": "👥 Фойдаланувчилар",
        "ru": "👥 Пользователи",
    },
    "adm_btn_unmatched": {
        "uz_latn": "🔍 Topilmagan",
        "uz_cyrl": "🔍 Топилмаган",
        "ru": "🔍 Ненайденные",
    },
    "adm_btn_add_shop": {
        "uz_latn": "➕ Do'kon qo'shish",
        "uz_cyrl": "➕ Дўкон қўшиш",
        "ru": "➕ Добавить магазин",
    },
    "adm_btn_admins": {
        "uz_latn": "👑 Adminlar",
        "uz_cyrl": "👑 Админлар",
        "ru": "👑 Администраторы",
    },
    "adm_btn_add_admin": {
        "uz_latn": "➕ Admin qo'shish",
        "uz_cyrl": "➕ Админ қўшиш",
        "ru": "➕ Добавить админа",
    },
    "adm_stats_body": {
        "uz_latn": (
            "📊 <b>Statistika</b>\n\n"
            "👥 Foydalanuvchilar: <b>{users}</b>\n"
            "🏪 Do'konlar: <b>{shops}</b>\n"
            "📦 Katalog SKU: <b>{skus}</b>\n"
            "🏷 Do'kon takliflari: <b>{offers}</b>\n"
            "🧾 Buyurtmalar: <b>{orders}</b>\n"
            "💰 Umumiy savdo: <b>{gmv} so'm</b>\n"
            "🔍 Topilmagan so'rovlar: <b>{unmatched}</b>"
        ),
        "uz_cyrl": (
            "📊 <b>Статистика</b>\n\n"
            "👥 Фойдаланувчилар: <b>{users}</b>\n"
            "🏪 Дўконлар: <b>{shops}</b>\n"
            "📦 Каталог SKU: <b>{skus}</b>\n"
            "🏷 Дўкон таклифлари: <b>{offers}</b>\n"
            "🧾 Буюртмалар: <b>{orders}</b>\n"
            "💰 Умумий савдо: <b>{gmv} сўм</b>\n"
            "🔍 Топилмаган сўровлар: <b>{unmatched}</b>"
        ),
        "ru": (
            "📊 <b>Статистика</b>\n\n"
            "👥 Пользователей: <b>{users}</b>\n"
            "🏪 Магазинов: <b>{shops}</b>\n"
            "📦 SKU в каталоге: <b>{skus}</b>\n"
            "🏷 Предложений: <b>{offers}</b>\n"
            "🧾 Заказов: <b>{orders}</b>\n"
            "💰 Оборот: <b>{gmv} сум</b>\n"
            "🔍 Ненайденных запросов: <b>{unmatched}</b>"
        ),
    },
    "adm_users_header": {
        "uz_latn": (
            "👥 <b>Foydalanuvchilar ({total} ta)</b>\n{by_role}\n\n" "Oxirgi ro'yxatdan o'tganlar:"
        ),
        "uz_cyrl": (
            "👥 <b>Фойдаланувчилар ({total} та)</b>\n{by_role}\n\n" "Охирги рўйхатдан ўтганлар:"
        ),
        "ru": "👥 <b>Пользователи ({total})</b>\n{by_role}\n\nПоследние зарегистрированные:",
    },
    "adm_products_header": {
        "uz_latn": "📦 <b>Katalog mahsulotlari ({count} ta ko'rsatildi):</b>\n",
        "uz_cyrl": "📦 <b>Каталог маҳсулотлари ({count} та кўрсатилди):</b>\n",
        "ru": "📦 <b>Товары каталога (показано {count}):</b>\n",
    },
    "adm_admins_header": {
        "uz_latn": "👑 <b>Adminlar:</b>\n",
        "uz_cyrl": "👑 <b>Админлар:</b>\n",
        "ru": "👑 <b>Администраторы:</b>\n",
    },
    "adm_ask_admin_id": {
        "uz_latn": (
            "👑 Yangi adminning Telegram ID raqamini yozing (faqat raqam).\n"
            "<i>Bekor qilish uchun /cancel.</i>"
        ),
        "uz_cyrl": (
            "👑 Янги админнинг Telegram ID рақамини ёзинг (фақат рақам).\n"
            "<i>Бекор қилиш учун /cancel.</i>"
        ),
        "ru": (
            "👑 Напишите Telegram ID нового админа (только цифры).\n" "<i>Для отмены /cancel.</i>"
        ),
    },
    "adm_admin_added": {
        "uz_latn": "✅ <code>{tg_id}</code> admin qilib tayinlandi.",
        "uz_cyrl": "✅ <code>{tg_id}</code> админ қилиб тайинланди.",
        "ru": "✅ <code>{tg_id}</code> назначен администратором.",
    },
    "adm_admin_not_found": {
        "uz_latn": (
            "❌ Bu ID bilan foydalanuvchi topilmadi. " "U avval botga /start yuborishi kerak."
        ),
        "uz_cyrl": (
            "❌ Бу ID билан фойдаланувчи топилмади. " "У аввал ботга /start юбориши керак."
        ),
        "ru": ("❌ Пользователь с таким ID не найден. " "Сначала он должен отправить боту /start."),
    },
    "adm_super_admin_only": {
        "uz_latn": "Bu amal faqat bosh admin uchun.",
        "uz_cyrl": "Бу амал фақат бош админ учун.",
        "ru": "Это действие только для главного администратора.",
    },
    "admin_panel_title": {
        "uz_latn": (
            "🛠 <b>Admin panel</b>\n\n"
            "• <b>Do'kon qo'shish:</b> /add_shop\n"
            "• <b>Do'konlar ro'yxati:</b> /shops\n"
            "• <b>Statistika:</b> /admin\n"
            "• <b>Topilmagan so'rovlar:</b> /unmatched"
        ),
        "uz_cyrl": (
            "🛠 <b>Админ панел</b>\n\n"
            "• <b>Дўкон қўшиш:</b> /add_shop\n"
            "• <b>Дўконлар рўйхати:</b> /shops\n"
            "• <b>Статистика:</b> /admin\n"
            "• <b>Топилмаган сўровлар:</b> /unmatched"
        ),
        "ru": (
            "🛠 <b>Админ-панель</b>\n\n"
            "• <b>Добавить магазин:</b> /add_shop\n"
            "• <b>Список магазинов:</b> /shops\n"
            "• <b>Статистика:</b> /admin\n"
            "• <b>Ненайденные запросы:</b> /unmatched"
        ),
    },
    "admin_only": {
        "uz_latn": "Bu bo'lim faqat adminlar uchun.",
        "uz_cyrl": "Бу бўлим фақат админлар учун.",
        "ru": "Этот раздел только для администраторов.",
    },
    "admin_shop_ask_name": {
        "uz_latn": "🏪 Yangi do'kon qo'shamiz.\n\nDo'kon nomini yozing:",
        "uz_cyrl": "🏪 Янги дўкон қўшамиз.\n\nДўкон номини ёзинг:",
        "ru": "🏪 Добавляем новый магазин.\n\nНапишите название магазина:",
    },
    "admin_shop_ask_phone": {
        "uz_latn": "📞 Do'kon telefon raqamini yozing:",
        "uz_cyrl": "📞 Дўкон телефон рақамини ёзинг:",
        "ru": "📞 Напишите телефон магазина:",
    },
    "admin_shop_ask_district": {
        "uz_latn": "📍 Do'kon tumanini tanlang:",
        "uz_cyrl": "📍 Дўкон туманини танланг:",
        "ru": "📍 Выберите район магазина:",
    },
    "admin_shop_ask_address": {
        "uz_latn": "🏠 Do'kon manzilini yozing:",
        "uz_cyrl": "🏠 Дўкон манзилини ёзинг:",
        "ru": "🏠 Напишите адрес магазина:",
    },
    "admin_shop_created": {
        "uz_latn": (
            "✅ <b>{name}</b> qo'shildi (ID: {shop_id}).\n\n"
            "Endi egalarining Telegram ID raqamlarini qo'shing."
        ),
        "uz_cyrl": (
            "✅ <b>{name}</b> қўшилди (ID: {shop_id}).\n\n"
            "Энди эгаларининг Telegram ID рақамларини қўшинг."
        ),
        "ru": (
            "✅ <b>{name}</b> добавлен (ID: {shop_id}).\n\n"
            "Теперь добавьте Telegram ID владельцев."
        ),
    },
    "admin_shop_ask_owner": {
        "uz_latn": (
            "👤 Egasining Telegram ID raqamini yozing (faqat raqam).\n"
            "<i>ID ni bilish uchun @userinfobot dan foydalaning.</i>"
        ),
        "uz_cyrl": (
            "👤 Эгасининг Telegram ID рақамини ёзинг (фақат рақам).\n"
            "<i>ID ни билиш учун @userinfobot дан фойдаланинг.</i>"
        ),
        "ru": (
            "👤 Напишите Telegram ID владельца (только цифры).\n"
            "<i>Узнать ID можно через @userinfobot.</i>"
        ),
    },
    "admin_owner_added": {
        "uz_latn": (
            "✅ Ega qo'shildi: <code>{tg_id}</code>\n\n"
            "Yana ega qo'shasizmi? ID yozing yoki /done bosing."
        ),
        "uz_cyrl": (
            "✅ Эга қўшилди: <code>{tg_id}</code>\n\n"
            "Яна эга қўшасизми? ID ёзинг ёки /done босинг."
        ),
        "ru": (
            "✅ Владелец добавлен: <code>{tg_id}</code>\n\n"
            "Добавить ещё? Напишите ID или нажмите /done."
        ),
    },
    "admin_owner_invalid": {
        "uz_latn": "❌ Telegram ID faqat raqamlardan iborat bo'lishi kerak. Qaytadan yozing:",
        "uz_cyrl": "❌ Telegram ID фақат рақамлардан иборат бўлиши керак. Қайтадан ёзинг:",
        "ru": "❌ Telegram ID должен состоять только из цифр. Напишите ещё раз:",
    },
    "admin_shop_done": {
        "uz_latn": "✅ <b>{name}</b> to'liq sozlandi. Egalari: {count} ta.",
        "uz_cyrl": "✅ <b>{name}</b> тўлиқ созланди. Эгалари: {count} та.",
        "ru": "✅ <b>{name}</b> полностью настроен. Владельцев: {count}.",
    },
    "admin_shops_header": {
        "uz_latn": "🏪 <b>Do'konlar ({count} ta):</b>\n",
        "uz_cyrl": "🏪 <b>Дўконлар ({count} та):</b>\n",
        "ru": "🏪 <b>Магазины ({count}):</b>\n",
    },
    "admin_shops_empty": {
        "uz_latn": "Hozircha do'konlar yo'q. /add_shop orqali qo'shing.",
        "uz_cyrl": "Ҳозирча дўконлар йўқ. /add_shop орқали қўшинг.",
        "ru": "Магазинов пока нет. Добавьте через /add_shop.",
    },
    "shp_btn_quick_price": {
        "uz_latn": "✏️ Tez narx yangilash",
        "uz_cyrl": "✏️ Тез нарх янгилаш",
        "ru": "✏️ Быстрое обновление цены",
    },
    "shp_btn_products": {
        "uz_latn": "📋 Mahsulotlarim",
        "uz_cyrl": "📋 Маҳсулотларим",
        "ru": "📋 Мои товары",
    },
    "shp_btn_add_product": {
        "uz_latn": "➕ Yangi mahsulot",
        "uz_cyrl": "➕ Янги маҳсулот",
        "ru": "➕ Новый товар",
    },
    "shp_btn_upload": {
        "uz_latn": "📤 Excel yuklash",
        "uz_cyrl": "📤 Excel юклаш",
        "ru": "📤 Загрузить Excel",
    },
    "shp_btn_template": {
        "uz_latn": "📄 Shablon olish",
        "uz_cyrl": "📄 Шаблон олиш",
        "ru": "📄 Скачать шаблон",
    },
    "shp_btn_delivery": {
        "uz_latn": "🚚 Yetkazish",
        "uz_cyrl": "🚚 Етказиш",
        "ru": "🚚 Доставка",
    },
    "shp_btn_orders": {
        "uz_latn": "📦 Buyurtmalar",
        "uz_cyrl": "📦 Буюртмалар",
        "ru": "📦 Заказы",
    },
    "shp_choose_shop": {
        "uz_latn": "🏪 Qaysi do'kon bilan ishlaymiz?",
        "uz_cyrl": "🏪 Қайси дўкон билан ишлаймиз?",
        "ru": "🏪 С каким магазином работаем?",
    },
    "shp_btn_switch_shop": {
        "uz_latn": "🔄 Do'konni almashtirish",
        "uz_cyrl": "🔄 Дўконни алмаштириш",
        "ru": "🔄 Сменить магазин",
    },
    "shp_quick_price_prompt": {
        "uz_latn": (
            "✏️ <b>Tez narx yangilash</b>\n\n"
            "Mahsulot nomi va yangi narxni bitta qatorda yozing:\n"
            "<code>cement m400 52000</code>\n\n"
            "<i>Bekor qilish uchun /cancel</i>"
        ),
        "uz_cyrl": (
            "✏️ <b>Тез нарх янгилаш</b>\n\n"
            "Маҳсулот номи ва янги нархни битта қаторда ёзинг:\n"
            "<code>cement m400 52000</code>\n\n"
            "<i>Бекор қилиш учун /cancel</i>"
        ),
        "ru": (
            "✏️ <b>Быстрое обновление цены</b>\n\n"
            "Напишите название товара и новую цену одной строкой:\n"
            "<code>cement m400 52000</code>\n\n"
            "<i>Для отмены /cancel</i>"
        ),
    },
    "shp_template_caption": {
        "uz_latn": (
            "📄 <b>Namuna fayl</b>\n\n"
            "Ustun nomlarini o'zgartirmang, namunadagi 3 qatorni o'z "
            "mahsulotlaringiz bilan almashtiring va faylni shu yerga qaytaring."
        ),
        "uz_cyrl": (
            "📄 <b>Намуна файл</b>\n\n"
            "Устун номларини ўзгартирманг, намунадаги 3 қаторни ўз "
            "маҳсулотларингиз билан алмаштиринг ва файлни шу ерга қайтаринг."
        ),
        "ru": (
            "📄 <b>Шаблон</b>\n\n"
            "Не меняйте названия столбцов, замените 3 строки примера своими "
            "товарами и отправьте файл сюда."
        ),
    },
    "shp_upload_prompt": {
        "uz_latn": "📤 Narxlar ro'yxati bilan Excel yoki CSV faylni shu yerga yuboring.",
        "uz_cyrl": "📤 Нархлар рўйхати билан Excel ёки CSV файлни шу ерга юборинг.",
        "ru": "📤 Отправьте сюда файл Excel или CSV со списком цен.",
    },
    "prod_btn_edit_price": {
        "uz_latn": "💰 Narxni o'zgartirish",
        "uz_cyrl": "💰 Нархни ўзгартириш",
        "ru": "💰 Изменить цену",
    },
    "prod_btn_edit_stock": {
        "uz_latn": "📦 Mavjudligi",
        "uz_cyrl": "📦 Мавжудлиги",
        "ru": "📦 Наличие",
    },
    "prod_btn_deactivate": {
        "uz_latn": "🚫 Sotuvdan olish",
        "uz_cyrl": "🚫 Сотувдан олиш",
        "ru": "🚫 Снять с продажи",
    },
    "prod_btn_activate": {
        "uz_latn": "✅ Sotuvga qaytarish",
        "uz_cyrl": "✅ Сотувга қайтариш",
        "ru": "✅ Вернуть в продажу",
    },
    "prod_stock_in_stock": {
        "uz_latn": "✅ Mavjud",
        "uz_cyrl": "✅ Мавжуд",
        "ru": "✅ В наличии",
    },
    "prod_stock_low": {
        "uz_latn": "🟡 Kam qoldi",
        "uz_cyrl": "🟡 Кам қолди",
        "ru": "🟡 Мало",
    },
    "prod_stock_on_order": {
        "uz_latn": "🔵 Buyurtma asosida",
        "uz_cyrl": "🔵 Буюртма асосида",
        "ru": "🔵 Под заказ",
    },
    "prod_stock_out": {
        "uz_latn": "🔴 Tugagan",
        "uz_cyrl": "🔴 Тугаган",
        "ru": "🔴 Нет в наличии",
    },
    "prod_card": {
        "uz_latn": (
            "📦 <b>{name}</b>\n\n"
            "💰 Narx: <b>{price} so'm</b> / {pack}\n"
            "📊 Holat: {stock}\n"
            "🔎 Sotuvda: {active}"
        ),
        "uz_cyrl": (
            "📦 <b>{name}</b>\n\n"
            "💰 Нарх: <b>{price} сўм</b> / {pack}\n"
            "📊 Ҳолат: {stock}\n"
            "🔎 Сотувда: {active}"
        ),
        "ru": (
            "📦 <b>{name}</b>\n\n"
            "💰 Цена: <b>{price} сум</b> / {pack}\n"
            "📊 Статус: {stock}\n"
            "🔎 В продаже: {active}"
        ),
    },
    "prod_ask_price": {
        "uz_latn": (
            "💰 <b>{name}</b> uchun yangi narxni yozing (so'm, {pack} uchun).\n"
            "<i>Bekor qilish uchun /cancel</i>"
        ),
        "uz_cyrl": (
            "💰 <b>{name}</b> учун янги нархни ёзинг (сўм, {pack} учун).\n"
            "<i>Бекор қилиш учун /cancel</i>"
        ),
        "ru": (
            "💰 Напишите новую цену для <b>{name}</b> (сум, за {pack}).\n"
            "<i>Для отмены /cancel</i>"
        ),
    },
    "prod_price_updated": {
        "uz_latn": "✅ Narx yangilandi: <b>{price} so'm</b>",
        "uz_cyrl": "✅ Нарх янгиланди: <b>{price} сўм</b>",
        "ru": "✅ Цена обновлена: <b>{price} сум</b>",
    },
    "prod_stock_updated": {
        "uz_latn": "✅ Holat yangilandi.",
        "uz_cyrl": "✅ Ҳолат янгиланди.",
        "ru": "✅ Статус обновлён.",
    },
    "prod_deactivated": {
        "uz_latn": "🚫 Mahsulot sotuvdan olindi.",
        "uz_cyrl": "🚫 Маҳсулот сотувдан олинди.",
        "ru": "🚫 Товар снят с продажи.",
    },
    "prod_activated": {
        "uz_latn": "✅ Mahsulot sotuvga qaytarildi.",
        "uz_cyrl": "✅ Маҳсулот сотувга қайтарилди.",
        "ru": "✅ Товар возвращён в продажу.",
    },
    "prod_yes": {"uz_latn": "ha", "uz_cyrl": "ҳа", "ru": "да"},
    "prod_no": {"uz_latn": "yo'q", "uz_cyrl": "йўқ", "ru": "нет"},
    "prod_not_yours": {
        "uz_latn": "Bu mahsulot sizning do'koningizga tegishli emas.",
        "uz_cyrl": "Бу маҳсулот сизнинг дўконингизга тегишли эмас.",
        "ru": "Этот товар не принадлежит вашему магазину.",
    },
    "not_shop_owner": {
        "uz_latn": "Siz do'kon egasi sifatida ro'yxatdan o'tmagansiz.",
        "uz_cyrl": "Сиз дўкон эгаси сифатида рўйхатдан ўтмагансиз.",
        "ru": "Вы не зарегистрированы как владелец магазина.",
    },
    # ── Product listing wizard ────────────────────────────────────────────
    "menu_add_product": {
        "uz_latn": "➕ Yangi mahsulot",
        "uz_cyrl": "➕ Янги маҳсулот",
        "ru": "➕ Новый товар",
    },
    "listing_quick_prompt": {
        "uz_latn": (
            "📷 Mahsulot rasm(lar)ini yuboring va izohga bir qatorda yozing:\n"
            "<b>nomi + qadoq + narx</b>\n\n"
            "<i>Masalan:</i>\n"
            "<code>Fanera berezovaya 3x3 12mm dona 157000 so'm</code>\n\n"
            "Rasmsiz ham bo'ladi — shunchaki matn yuboring."
        ),
        "uz_cyrl": (
            "📷 Маҳсулот расм(лар)ини юборинг ва изоҳга бир қаторда ёзинг:\n"
            "<b>номи + қадоқ + нарх</b>\n\n"
            "<i>Масалан:</i>\n"
            "<code>Fanera berezovaya 3x3 12mm дона 157000 сўм</code>\n\n"
            "Расмсиз ҳам бўлади — шунчаки матн юборинг."
        ),
        "ru": (
            "📷 Отправьте фото товара и в подписи одной строкой укажите:\n"
            "<b>название + фасовка + цена</b>\n\n"
            "<i>Например:</i>\n"
            "<code>Фанера березовая 3х3 12мм шт 157000 сум</code>\n\n"
            "Можно и без фото — просто отправьте текст."
        ),
    },
    "listing_ask_name": {
        "uz_latn": "Mahsulot nomini yozing:",
        "uz_cyrl": "Маҳсулот номини ёзинг:",
        "ru": "Напишите название товара:",
    },
    "listing_ask_price": {
        "uz_latn": "<b>{name}</b> — narxi qancha? Faqat raqam yozing.",
        "uz_cyrl": "<b>{name}</b> — нархи қанча? Фақат рақам ёзинг.",
        "ru": "<b>{name}</b> — какая цена? Напишите только число.",
    },
    "listing_ask_pack": {
        "uz_latn": "Qanday qadoqda sotasiz?",
        "uz_cyrl": "Қандай қадоқда сотасиз?",
        "ru": "В какой фасовке продаёте?",
    },
    "listing_ask_pack_custom": {
        "uz_latn": "Qadoqni yozing. <i>Masalan: 25kg yoki 10 litr</i>",
        "uz_cyrl": "Қадоқни ёзинг. <i>Масалан: 25kg ёки 10 литр</i>",
        "ru": "Напишите фасовку. <i>Например: 25кг или 10 литр</i>",
    },
    "listing_confirm_price": {
        "uz_latn": ("Narxni shunday tushundim: <b>{price} so'm</b> / {pack}\n" "To'g'rimi?"),
        "uz_cyrl": ("Нархни шундай тушундим: <b>{price} сўм</b> / {pack}\n" "Тўғрими?"),
        "ru": ("Я понял цену так: <b>{price} сум</b> / {pack}\n" "Верно?"),
    },
    "listing_price_hint_explicit": {
        "uz_latn": (
            "Keyingi safar narxni <code>so'm</code> deb belgilang — "
            "shunda tasdiqlash so'ralmaydi."
        ),
        "uz_cyrl": (
            "Кейинги сафар нархни <code>сўм</code> деб белгиланг — " "шунда тасдиқлаш сўралмайди."
        ),
        "ru": (
            "В следующий раз пометьте цену словом <code>сум</code> — "
            "тогда подтверждение не потребуется."
        ),
    },
    "listing_photo_added": {
        "uz_latn": "📷 Rasm qo'shildi ({n}/{max}).",
        "uz_cyrl": "📷 Расм қўшилди ({n}/{max}).",
        "ru": "📷 Фото добавлено ({n}/{max}).",
    },
    "btn_price_correct": {
        "uz_latn": "✅ To'g'ri",
        "uz_cyrl": "✅ Тўғри",
        "ru": "✅ Верно",
    },
    "btn_price_fix": {
        "uz_latn": "✏️ Narxni tuzatish",
        "uz_cyrl": "✏️ Нархни тузатиш",
        "ru": "✏️ Исправить цену",
    },
    "btn_pack_other": {
        "uz_latn": "✏️ Boshqa",
        "uz_cyrl": "✏️ Бошқа",
        "ru": "✏️ Другая",
    },
    "listing_intro": {
        "uz_latn": (
            "Yangi mahsulot qo'shamiz. Har bir javobingiz darhol saqlanadi — "
            "istalgan payt to'xtab, keyin davom ettirsangiz bo'ladi."
        ),
        "uz_cyrl": (
            "Янги маҳсулот қўшамиз. Ҳар бир жавобингиз дарҳол сақланади — "
            "исталган пайт тўхтаб, кейин давом эттирсангиз бўлади."
        ),
        "ru": (
            "Добавляем новый товар. Каждый ваш ответ сохраняется сразу — "
            "можете прерваться в любой момент и продолжить позже."
        ),
    },
    "listing_resume_found": {
        "uz_latn": "Sizda tugallanmagan mahsulot bor: <b>{name}</b>\nDavom ettiramizmi?",
        "uz_cyrl": "Сизда тугалланмаган маҳсулот бор: <b>{name}</b>\nДавом эттирамизми?",
        "ru": "У вас есть незавершённый товар: <b>{name}</b>\nПродолжим?",
    },
    "listing_resumed": {
        "uz_latn": "Davom ettiramiz. Saqlangan ma'lumotlaringiz joyida.",
        "uz_cyrl": "Давом эттирамиз. Сақланган маълумотларингиз жойида.",
        "ru": "Продолжаем. Все сохранённые данные на месте.",
    },
    "listing_step_category": {
        "uz_latn": "1/7 — Mahsulot kategoriyasini tanlang:",
        "uz_cyrl": "1/7 — Маҳсулот категориясини танланг:",
        "ru": "1/7 — Выберите категорию товара:",
    },
    "listing_step_subcategory": {
        "uz_latn": "Aniqroq turini tanlang:",
        "uz_cyrl": "Аниқроқ турини танланг:",
        "ru": "Выберите подкатегорию:",
    },
    "listing_step_name": {
        "uz_latn": ("2/7 — Mahsulot nomini yozing.\n" "<i>Masalan: Fanera berezovaya 3x3 12mm</i>"),
        "uz_cyrl": ("2/7 — Маҳсулот номини ёзинг.\n" "<i>Масалан: Fanera berezovaya 3x3 12mm</i>"),
        "ru": ("2/7 — Напишите название товара.\n" "<i>Например: Фанера березовая 3х3 12мм</i>"),
    },
    "listing_step_unit": {
        "uz_latn": (
            "3/7 — Qadoq o'lchovini tanlang.\n"
            "<i>Bu narxni solishtirish uchun kerak: 50 kg li qop 52 000 so'm — "
            "bu 1 kg uchun 1 040 so'm degani.</i>"
        ),
        "uz_cyrl": (
            "3/7 — Қадоқ ўлчовини танланг.\n"
            "<i>Бу нархни солиштириш учун керак: 50 кг ли қоп 52 000 сўм — "
            "бу 1 кг учун 1 040 сўм дегани.</i>"
        ),
        "ru": (
            "3/7 — Выберите единицу фасовки.\n"
            "<i>Это нужно для сравнения цен: мешок 50 кг за 52 000 сум — "
            "это 1 040 сум за 1 кг.</i>"
        ),
    },
    "listing_step_pack_size": {
        "uz_latn": (
            "Bitta qadoq (qop/quti/rulon) ichida necha <b>{unit}</b> bor?\n"
            "<i>Masalan: bitta fanera listi uchun — 1</i>"
        ),
        "uz_cyrl": (
            "Битта қадоқ (қоп/қути/рулон) ичида неча <b>{unit}</b> бор?\n"
            "<i>Масалан: битта фанера листи учун — 1</i>"
        ),
        "ru": (
            "Сколько <b>{unit}</b> в одной упаковке (мешок/коробка/рулон)?\n"
            "<i>Например: для одного листа фанеры — 1</i>"
        ),
    },
    "listing_step_price": {
        "uz_latn": "4/7 — Bitta <b>{pack}</b> narxi qancha (so'm)? Faqat raqam yozing.",
        "uz_cyrl": "4/7 — Битта <b>{pack}</b> нархи қанча (сўм)? Фақат рақам ёзинг.",
        "ru": "4/7 — Цена за <b>{pack}</b> (сум)? Напишите только число.",
    },
    "listing_step_qty": {
        "uz_latn": "5/7 — Omborda nechta bor? Bilmasangiz — o'tkazib yuboring.",
        "uz_cyrl": "5/7 — Омборда нечта бор? Билмасангиз — ўтказиб юборинг.",
        "ru": "5/7 — Сколько есть на складе? Не знаете — пропустите.",
    },
    "listing_step_description": {
        "uz_latn": "6/7 — Qisqacha tavsif yozing (ixtiyoriy).",
        "uz_cyrl": "6/7 — Қисқача тавсиф ёзинг (ихтиёрий).",
        "ru": "6/7 — Напишите краткое описание (необязательно).",
    },
    "listing_step_photo": {
        "uz_latn": (
            "7/7 — {n}-rasmni yuboring ({hint}).\n" "Jami {max} tagacha rasm qo'shishingiz mumkin."
        ),
        "uz_cyrl": (
            "7/7 — {n}-расмни юборинг ({hint}).\n" "Жами {max} тагача расм қўшишингиз мумкин."
        ),
        "ru": ("7/7 — Отправьте фото №{n} ({hint}).\n" "Всего можно добавить до {max} фото."),
    },
    "listing_photo_hint_1": {
        "uz_latn": "old tomondan",
        "uz_cyrl": "олд томондан",
        "ru": "спереди",
    },
    "listing_photo_hint_2": {
        "uz_latn": "yon tomondan",
        "uz_cyrl": "ён томондан",
        "ru": "сбоку",
    },
    "listing_photo_hint_3": {
        "uz_latn": "yorliq yoki marka ko'rinadigan qilib",
        "uz_cyrl": "ёрлиқ ёки марка кўринадиган қилиб",
        "ru": "чтобы была видна этикетка или марка",
    },
    "listing_photo_saved": {
        "uz_latn": "✅ {n}-rasm saqlandi.",
        "uz_cyrl": "✅ {n}-расм сақланди.",
        "ru": "✅ Фото №{n} сохранено.",
    },
    "listing_photo_limit_reached": {
        "uz_latn": "Rasmlar to'liq ({max} ta). Saqlashga o'tamiz.",
        "uz_cyrl": "Расмлар тўлиқ ({max} та). Сақлашга ўтамиз.",
        "ru": "Фото загружены полностью ({max}). Переходим к сохранению.",
    },
    "listing_photo_duplicate": {
        "uz_latn": "Bu rasm allaqachon qo'shilgan. Boshqa rakursdan yuboring.",
        "uz_cyrl": "Бу расм аллақачон қўшилган. Бошқа ракурсдан юборинг.",
        "ru": "Это фото уже добавлено. Отправьте другой ракурс.",
    },
    "listing_photo_too_big": {
        "uz_latn": "Rasm juda katta. Kichikroq rasm yuboring.",
        "uz_cyrl": "Расм жуда катта. Кичикроқ расм юборинг.",
        "ru": "Фото слишком большое. Отправьте файл поменьше.",
    },
    "listing_review_title": {
        "uz_latn": "📦 <b>Tekshirib chiqing</b>",
        "uz_cyrl": "📦 <b>Текшириб чиқинг</b>",
        "ru": "📦 <b>Проверьте данные</b>",
    },
    "listing_matched_as": {
        "uz_latn": "🔗 Katalogda: <b>{name}</b>",
        "uz_cyrl": "🔗 Каталогда: <b>{name}</b>",
        "ru": "🔗 В каталоге: <b>{name}</b>",
    },
    "listing_not_matched": {
        "uz_latn": (
            "⚠️ Bu mahsulot katalogimizda topilmadi. Saqlaymiz va administrator "
            "tez orada katalogga qo'shadi — shundan keyin xaridorlarga ko'rina boshlaydi."
        ),
        "uz_cyrl": (
            "⚠️ Бу маҳсулот каталогимизда топилмади. Сақлаймиз ва администратор "
            "тез орада каталогга қўшади — шундан кейин харидорларга кўрина бошлайди."
        ),
        "ru": (
            "⚠️ Этот товар не найден в нашем каталоге. Мы сохраним его, и администратор "
            "скоро добавит в каталог — после этого он появится у покупателей."
        ),
    },
    "listing_saved": {
        "uz_latn": "✅ <b>{name}</b> saqlandi.",
        "uz_cyrl": "✅ <b>{name}</b> сақланди.",
        "ru": "✅ <b>{name}</b> сохранён.",
    },
    "listing_saved_pending_media": {
        "uz_latn": "Rasmlar administrator tekshiruvidan so'ng xaridorlarga ko'rsatiladi.",
        "uz_cyrl": "Расмлар администратор текширувидан сўнг харидорларга кўрсатилади.",
        "ru": "Фото будут показаны покупателям после проверки администратором.",
    },
    "listing_cancelled": {
        "uz_latn": "Bekor qilindi. Kiritilgan ma'lumotlar saqlanib qoldi.",
        "uz_cyrl": "Бекор қилинди. Киритилган маълумотлар сақланиб қолди.",
        "ru": "Отменено. Введённые данные сохранены.",
    },
    "listing_discarded": {
        "uz_latn": "Qoralama o'chirildi.",
        "uz_cyrl": "Қоралама ўчирилди.",
        "ru": "Черновик удалён.",
    },
    "listing_err_number": {
        "uz_latn": "Faqat raqam yuboring. Masalan: 52000",
        "uz_cyrl": "Фақат рақам юборинг. Масалан: 52000",
        "ru": "Отправьте только число. Например: 52000",
    },
    "listing_err_positive": {
        "uz_latn": "Qiymat noldan katta bo'lishi kerak.",
        "uz_cyrl": "Қиймат нолдан катта бўлиши керак.",
        "ru": "Значение должно быть больше нуля.",
    },
    "listing_err_negative_qty": {
        "uz_latn": "Miqdor manfiy bo'lishi mumkin emas.",
        "uz_cyrl": "Миқдор манфий бўлиши мумкин эмас.",
        "ru": "Количество не может быть отрицательным.",
    },
    "listing_err_name_empty": {
        "uz_latn": "Mahsulot nomini yozing.",
        "uz_cyrl": "Маҳсулот номини ёзинг.",
        "ru": "Напишите название товара.",
    },
    "listing_err_name_too_long": {
        "uz_latn": "Nom juda uzun. Qisqartiring.",
        "uz_cyrl": "Ном жуда узун. Қисқартиринг.",
        "ru": "Название слишком длинное. Сократите.",
    },
    "listing_err_description_too_long": {
        "uz_latn": "Tavsif juda uzun. Qisqartiring.",
        "uz_cyrl": "Тавсиф жуда узун. Қисқартиринг.",
        "ru": "Описание слишком длинное. Сократите.",
    },
    "listing_err_unit": {
        "uz_latn": "O'lchov birligi noto'g'ri. Ro'yxatdan tanlang.",
        "uz_cyrl": "Ўлчов бирлиги нотўғри. Рўйхатдан танланг.",
        "ru": "Неверная единица измерения. Выберите из списка.",
    },
    "listing_err_incompatible_unit": {
        "uz_latn": ("Bu o'lchov tanlangan mahsulotga to'g'ri kelmaydi. Boshqa o'lchov tanlang."),
        "uz_cyrl": ("Бу ўлчов танланган маҳсулотга тўғри келмайди. Бошқа ўлчов танланг."),
        "ru": "Эта единица не подходит к выбранному товару. Выберите другую.",
    },
    "listing_err_photo_failed": {
        "uz_latn": "Rasmni saqlab bo'lmadi. Yana bir marta yuboring.",
        "uz_cyrl": "Расмни сақлаб бўлмади. Яна бир марта юборинг.",
        "ru": "Не удалось сохранить фото. Отправьте ещё раз.",
    },
    "listing_err_incomplete": {
        "uz_latn": "Ma'lumotlar to'liq emas — davom ettiramiz.",
        "uz_cyrl": "Маълумотлар тўлиқ эмас — давом эттирамиз.",
        "ru": "Данные неполные — продолжим заполнение.",
    },
    "listing_label_price": {
        "uz_latn": "Narx",
        "uz_cyrl": "Нарх",
        "ru": "Цена",
    },
    "listing_label_unit_price": {
        "uz_latn": "1 {unit} uchun",
        "uz_cyrl": "1 {unit} учун",
        "ru": "за 1 {unit}",
    },
    "listing_label_stock": {
        "uz_latn": "Omborda",
        "uz_cyrl": "Омборда",
        "ru": "На складе",
    },
    "listing_label_photos": {
        "uz_latn": "Rasmlar",
        "uz_cyrl": "Расмлар",
        "ru": "Фото",
    },
    "listing_stock_in_stock": {
        "uz_latn": "✅ Mavjud",
        "uz_cyrl": "✅ Мавжуд",
        "ru": "✅ В наличии",
    },
    "listing_stock_low": {
        "uz_latn": "⚠️ Kam qoldi",
        "uz_cyrl": "⚠️ Кам қолди",
        "ru": "⚠️ Мало осталось",
    },
    "listing_stock_on_order": {
        "uz_latn": "🕒 Buyurtma asosida",
        "uz_cyrl": "🕒 Буюртма асосида",
        "ru": "🕒 Под заказ",
    },
    "listing_stock_out": {
        "uz_latn": "❌ Tugagan",
        "uz_cyrl": "❌ Тугаган",
        "ru": "❌ Нет в наличии",
    },
    "btn_listing_save": {
        "uz_latn": "✅ Saqlash",
        "uz_cyrl": "✅ Сақлаш",
        "ru": "✅ Сохранить",
    },
    "btn_listing_edit": {
        "uz_latn": "✏️ Tahrirlash",
        "uz_cyrl": "✏️ Таҳрирлаш",
        "ru": "✏️ Редактировать",
    },
    "btn_listing_add_photo": {
        "uz_latn": "📷 Yana rasm",
        "uz_cyrl": "📷 Яна расм",
        "ru": "📷 Ещё фото",
    },
    "btn_listing_photos_done": {
        "uz_latn": "✅ Rasmlar tayyor",
        "uz_cyrl": "✅ Расмлар тайёр",
        "ru": "✅ Фото готовы",
    },
    "btn_listing_resume": {
        "uz_latn": "▶️ Davom ettirish",
        "uz_cyrl": "▶️ Давом эттириш",
        "ru": "▶️ Продолжить",
    },
    "btn_listing_start_new": {
        "uz_latn": "🆕 Yangisini boshlash",
        "uz_cyrl": "🆕 Янгисини бошлаш",
        "ru": "🆕 Начать новый",
    },
    "btn_listing_another": {
        "uz_latn": "➕ Yana mahsulot",
        "uz_cyrl": "➕ Яна маҳсулот",
        "ru": "➕ Ещё товар",
    },
    "btn_view_photos": {
        "uz_latn": "📷 Rasmlarni ko'rish",
        "uz_cyrl": "📷 Расмларни кўриш",
        "ru": "📷 Посмотреть фото",
    },
    "photos_unavailable": {
        "uz_latn": "Bu variant uchun rasm yo'q.",
        "uz_cyrl": "Бу вариант учун расм йўқ.",
        "ru": "Для этого варианта нет фото.",
    },
    # --- Catalogue browsing (customer + admin) ---
    # Checkout's own version of request_location. Telegram Desktop cannot
    # share a location at all, so the prompt has to say up front that typing
    # the address works -- otherwise a desktop customer sees only a button
    # that errors.
    "request_location_checkout": {
        "uz_latn": (
            "📍 Yetkazib berish manzilini yuboring.\n\n"
            "Lokatsiya tugmasini bosing yoki manzilni shunchaki yozib yuboring."
        ),
        "uz_cyrl": (
            "📍 Етказиб бериш манзилини юборинг.\n\n"
            "Локация тугмасини босинг ёки манзилни шунчаки ёзиб юборинг."
        ),
        "ru": (
            "📍 Отправьте адрес доставки.\n\n"
            "Нажмите кнопку геолокации или просто напишите адрес текстом."
        ),
    },
    "currency_suffix": {
        "uz_latn": "so'm",
        "uz_cyrl": "сўм",
        "ru": "сум",
    },
    "btn_all_products": {
        "uz_latn": "📋 Barcha mahsulotlar",
        "uz_cyrl": "📋 Барча маҳсулотлар",
        "ru": "📋 Все товары",
    },
    "all_products_header": {
        "uz_latn": "📦 <b>Barcha mahsulotlar ({count} ta)</b>\n",
        "uz_cyrl": "📦 <b>Барча маҳсулотлар ({count} та)</b>\n",
        "ru": "📦 <b>Все товары ({count})</b>\n",
    },
    # Shown instead of a number wherever the price list says the price is
    # agreed per order rather than published.
    "price_negotiable": {
        "uz_latn": "Kelishiladi",
        "uz_cyrl": "Келишилади",
        "ru": "Договорная",
    },
    # A price that comes from the supplier's list rather than a live shop
    # offer. Marked so nobody reads it as a firm quote.
    "price_reference_hint": {
        "uz_latn": "<i>~ belgisi — yetkazib beruvchi prays-listidagi narx.</i>",
        "uz_cyrl": "<i>~ белгиси — етказиб берувчи прайс-листидаги нарх.</i>",
        "ru": "<i>~ — цена из прайс-листа поставщика.</i>",
    },
    # --- Quote screen ---
    "btn_back_to_basket": {
        "uz_latn": "◀️ Savatga qaytish",
        "uz_cyrl": "◀️ Саватга қайтиш",
        "ru": "◀️ Назад в корзину",
    },
    "quote_not_orderable": {
        "uz_latn": (
            "❌ Bu variantda birorta mahsulot topilmadi, shuning uchun buyurtma "
            "berib bo'lmaydi.\n\nSavatni tahrirlab, mahsulot nomlarini "
            "aniqroq yozib ko'ring."
        ),
        "uz_cyrl": (
            "❌ Бу вариантда бирорта маҳсулот топилмади, шунинг учун буюртма "
            "бериб бўлмайди.\n\nСаватни таҳрирлаб, маҳсулот номларини "
            "аниқроқ ёзиб кўринг."
        ),
        "ru": (
            "❌ В этом варианте не найдено ни одного товара, поэтому заказ "
            "оформить нельзя.\n\nОтредактируйте корзину и укажите названия "
            "точнее."
        ),
    },
    # --- Checkout: phone ---
    "error_invalid_phone": {
        "uz_latn": (
            "❌ Telefon raqam noto'g'ri.\n"
            "Namuna: <code>+998901234567</code> yoki <code>901234567</code>"
        ),
        "uz_cyrl": (
            "❌ Телефон рақам нотўғри.\n"
            "Намуна: <code>+998901234567</code> ёки <code>901234567</code>"
        ),
        "ru": (
            "❌ Неверный номер телефона.\n"
            "Пример: <code>+998901234567</code> или <code>901234567</code>"
        ),
    },
    # --- Checkout: address ---
    "btn_type_address_instead": {
        "uz_latn": "✍️ Manzilni yozib yuboraman",
        "uz_cyrl": "✍️ Манзилни ёзиб юбораман",
        "ru": "✍️ Напишу адрес текстом",
    },
    "prompt_type_address": {
        "uz_latn": (
            "✍️ Yetkazib berish manzilini yozing.\n"
            "<i>Masalan: Chilonzor tumani, Bunyodkor ko'chasi 12-uy.</i>"
        ),
        "uz_cyrl": (
            "✍️ Етказиб бериш манзилини ёзинг.\n"
            "<i>Масалан: Чилонзор тумани, Бунёдкор кўчаси 12-уй.</i>"
        ),
        "ru": (
            "✍️ Напишите адрес доставки.\n"
            "<i>Например: Чиланзарский район, улица Бунёдкор, дом 12.</i>"
        ),
    },
    "error_address_too_short": {
        "uz_latn": (
            "❌ Manzil juda qisqa. Tuman, ko'cha va uy raqamini yozing.\n"
            "<i>Masalan: Yunusobod tumani, Amir Temur 15-uy.</i>"
        ),
        "uz_cyrl": (
            "❌ Манзил жуда қисқа. Туман, кўча ва уй рақамини ёзинг.\n"
            "<i>Масалан: Юнусобод тумани, Амир Темур 15-уй.</i>"
        ),
        "ru": (
            "❌ Адрес слишком короткий. Укажите район, улицу и дом.\n"
            "<i>Например: Юнусабадский район, Амир Темур 15.</i>"
        ),
    },
    # ══════════════════════════════════════════════════════════════════════
    # Web storefront (app/web/storefront). Deliberately a separate key space
    # from the bot's: these strings are rendered into HTML by Jinja, which
    # escapes them, so unlike the bot catalogue above they must carry no
    # markup of their own.
    # ══════════════════════════════════════════════════════════════════════
    "web_tagline": {
        "uz_latn": "Qurilish mollari — bitta ro'yxat, eng arzon narx",
        "uz_cyrl": "Қурилиш моллари — битта рўйхат, энг арзон нарх",
        "ru": "Стройматериалы — один список, лучшая цена",
    },
    "web_nav_home": {"uz_latn": "Bosh sahifa", "uz_cyrl": "Бош саҳифа", "ru": "Главная"},
    "web_nav_catalog": {"uz_latn": "Katalog", "uz_cyrl": "Каталог", "ru": "Каталог"},
    "web_nav_basket": {"uz_latn": "Savat", "uz_cyrl": "Сават", "ru": "Корзина"},
    "web_nav_orders": {"uz_latn": "Buyurtmalar", "uz_cyrl": "Буюртмалар", "ru": "Заказы"},
    "web_nav_account": {"uz_latn": "Kabinet", "uz_cyrl": "Кабинет", "ru": "Кабинет"},
    "web_nav_shop": {"uz_latn": "Do'kon", "uz_cyrl": "Дўкон", "ru": "Магазин"},
    "web_login": {"uz_latn": "Kirish", "uz_cyrl": "Кириш", "ru": "Войти"},
    "web_logout": {"uz_latn": "Chiqish", "uz_cyrl": "Чиқиш", "ru": "Выйти"},
    "web_back": {"uz_latn": "Orqaga", "uz_cyrl": "Орқага", "ru": "Назад"},
    "web_save": {"uz_latn": "Saqlash", "uz_cyrl": "Сақлаш", "ru": "Сохранить"},
    "web_delete": {"uz_latn": "O'chirish", "uz_cyrl": "Ўчириш", "ru": "Удалить"},
    "web_saved": {"uz_latn": "Saqlandi", "uz_cyrl": "Сақланди", "ru": "Сохранено"},
    "web_currency": {"uz_latn": "so'm", "uz_cyrl": "сўм", "ru": "сум"},
    "web_loading": {"uz_latn": "Hisoblanmoqda…", "uz_cyrl": "Ҳисобланмоқда…", "ru": "Считаем…"},
    "web_error_generic": {
        "uz_latn": "Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
        "uz_cyrl": "Хатолик юз берди. Бироздан сўнг қайта уриниб кўринг.",
        "ru": "Произошла ошибка. Попробуйте ещё раз чуть позже.",
    },
    "web_not_found": {
        "uz_latn": "Sahifa topilmadi.",
        "uz_cyrl": "Саҳифа топилмади.",
        "ru": "Страница не найдена.",
    },
    # ── Home ──────────────────────────────────────────────────────────────
    "web_home_title": {
        "uz_latn": "Ro'yxatingizni yozing — narxini biz topamiz",
        "uz_cyrl": "Рўйхатингизни ёзинг — нархини биз топамиз",
        "ru": "Напишите список — цену найдём мы",
    },
    "web_home_subtitle": {
        "uz_latn": (
            "Kerakli qurilish mollarini xohlagancha yozing. Biz ularni topamiz, "
            "eng arzon variantni jamlaymiz va yetkazib beramiz."
        ),
        "uz_cyrl": (
            "Керакли қурилиш молларини хоҳлаганча ёзинг. Биз уларни топамиз, "
            "энг арзон вариантни жамлаймиз ва етказиб берамиз."
        ),
        "ru": (
            "Напишите нужные стройматериалы как удобно. Мы найдём их, соберём "
            "самый выгодный вариант и доставим."
        ),
    },
    "web_home_placeholder": {
        "uz_latn": "10 dona fanera 12mm, 5 dona osb 9mm, 20 dona dvp 3.2",
        "uz_cyrl": "10 дона фанера 12мм, 5 дона осб 9мм, 20 дона двп 3.2",
        "ru": "10 шт фанера 12мм, 5 шт осб 9мм, 20 шт двп 3.2",
    },
    "web_home_cta": {
        "uz_latn": "Narxlarni hisoblash",
        "uz_cyrl": "Нархларни ҳисоблаш",
        "ru": "Рассчитать цены",
    },
    "web_home_example": {"uz_latn": "Namuna", "uz_cyrl": "Намуна", "ru": "Пример"},
    "web_home_how": {
        "uz_latn": "Qanday ishlaydi",
        "uz_cyrl": "Қандай ишлайди",
        "ru": "Как это работает",
    },
    "web_home_step1_title": {
        "uz_latn": "Ro'yxat yuboring",
        "uz_cyrl": "Рўйхат юборинг",
        "ru": "Отправьте список",
    },
    "web_home_step1_body": {
        "uz_latn": "Erkin matnda — lotin, kirill yoki ruscha, aralash bo'lsa ham.",
        "uz_cyrl": "Эркин матнда — лотин, кирилл ёки русча, аралаш бўлса ҳам.",
        "ru": "Свободным текстом — латиницей, кириллицей или по-русски, можно вперемешку.",
    },
    "web_home_step2_title": {
        "uz_latn": "Variantni tanlang",
        "uz_cyrl": "Вариантни танланг",
        "ru": "Выберите вариант",
    },
    "web_home_step2_body": {
        "uz_latn": "Yetkazib berish bilan birga hisoblangan variantlarni solishtiring.",
        "uz_cyrl": "Етказиб бериш билан бирга ҳисобланган вариантларни солиштиринг.",
        "ru": "Сравните варианты, посчитанные вместе с доставкой.",
    },
    "web_home_step3_title": {
        "uz_latn": "Buyurtma bering",
        "uz_cyrl": "Буюртма беринг",
        "ru": "Оформите заказ",
    },
    "web_home_step3_body": {
        "uz_latn": "Manzilni tanlang — qolganini biz bajaramiz.",
        "uz_cyrl": "Манзилни танланг — қолганини биз бажарамиз.",
        "ru": "Выберите адрес — остальное сделаем мы.",
    },
    "web_home_categories": {
        "uz_latn": "Bo'limlar",
        "uz_cyrl": "Бўлимлар",
        "ru": "Разделы",
    },
    # ── Catalog ───────────────────────────────────────────────────────────
    "web_catalog_title": {"uz_latn": "Katalog", "uz_cyrl": "Каталог", "ru": "Каталог"},
    "web_catalog_empty": {
        "uz_latn": "Hozircha bu bo'limda mahsulot yo'q.",
        "uz_cyrl": "Ҳозирча бу бўлимда маҳсулот йўқ.",
        "ru": "В этом разделе пока нет товаров.",
    },
    "web_price_from": {"uz_latn": "narxi", "uz_cyrl": "нархи", "ru": "цена"},
    "web_product_no_offers": {
        "uz_latn": "Narx hozircha mavjud emas",
        "uz_cyrl": "Нарх ҳозирча мавжуд эмас",
        "ru": "Цена пока недоступна",
    },
    "web_product_brand": {"uz_latn": "Brend", "uz_cyrl": "Бренд", "ru": "Бренд"},
    "web_product_unit": {"uz_latn": "O'lchov", "uz_cyrl": "Ўлчов", "ru": "Единица"},
    "web_add_to_basket": {
        "uz_latn": "Savatga qo'shish",
        "uz_cyrl": "Саватга қўшиш",
        "ru": "В корзину",
    },
    "web_qty": {"uz_latn": "Miqdor", "uz_cyrl": "Миқдор", "ru": "Количество"},
    "web_added_to_basket": {
        "uz_latn": "Savatga qo'shildi",
        "uz_cyrl": "Саватга қўшилди",
        "ru": "Добавлено в корзину",
    },
    # ── Basket ────────────────────────────────────────────────────────────
    "web_basket_title": {"uz_latn": "Savat", "uz_cyrl": "Сават", "ru": "Корзина"},
    "web_basket_empty": {
        "uz_latn": "Savat bo'sh.",
        "uz_cyrl": "Сават бўш.",
        "ru": "Корзина пуста.",
    },
    "web_basket_empty_hint": {
        "uz_latn": "Ro'yxatingizni yozing yoki katalogdan tanlang.",
        "uz_cyrl": "Рўйхатингизни ёзинг ёки каталогдан танланг.",
        "ru": "Напишите список или выберите из каталога.",
    },
    "web_basket_count": {
        "uz_latn": "{count} ta mahsulot",
        "uz_cyrl": "{count} та маҳсулот",
        "ru": "товаров: {count}",
    },
    "web_basket_choose_kind": {
        "uz_latn": "turini tanlang",
        "uz_cyrl": "турини танланг",
        "ru": "уточните вид",
    },
    "web_basket_not_found": {
        "uz_latn": "katalogda topilmadi",
        "uz_cyrl": "каталогда топилмади",
        "ru": "нет в каталоге",
    },
    "web_basket_add_more": {
        "uz_latn": "Yana qo'shish",
        "uz_cyrl": "Яна қўшиш",
        "ru": "Добавить ещё",
    },
    "web_basket_clear": {"uz_latn": "Tozalash", "uz_cyrl": "Тозалаш", "ru": "Очистить"},
    "web_basket_calculate": {
        "uz_latn": "Narxlarni hisoblash",
        "uz_cyrl": "Нархларни ҳисоблаш",
        "ru": "Рассчитать цены",
    },
    "web_basket_parse_failed": {
        "uz_latn": (
            "Ro'yxatni tushunolmadik. Har bir qatorda miqdor va nomni yozing, "
            "masalan: «10 dona fanera 12mm»."
        ),
        "uz_cyrl": (
            "Рўйхатни тушунолмадик. Ҳар бир қаторда миқдор ва номни ёзинг, "
            "масалан: «10 дона фанера 12мм»."
        ),
        "ru": (
            "Не удалось разобрать список. Укажите в строке количество и название, "
            "например: «10 шт фанера 12мм»."
        ),
    },
    "web_basket_nothing_confirmed": {
        "uz_latn": "Hisoblash uchun kamida bitta tasdiqlangan mahsulot kerak.",
        "uz_cyrl": "Ҳисоблаш учун камида битта тасдиқланган маҳсулот керак.",
        "ru": "Для расчёта нужен хотя бы один подтверждённый товар.",
    },
    # ── Quote ─────────────────────────────────────────────────────────────
    "web_quote_title": {"uz_latn": "Takliflar", "uz_cyrl": "Таклифлар", "ru": "Предложения"},
    "web_quote_empty": {
        "uz_latn": "Bu mahsulotlar bo'yicha hozircha taklif topilmadi.",
        "uz_cyrl": "Бу маҳсулотлар бўйича ҳозирча таклиф топилмади.",
        "ru": "По этим товарам пока нет предложений.",
    },
    "web_quote_cheapest": {
        "uz_latn": "Eng tejamli",
        "uz_cyrl": "Энг тежамли",
        "ru": "Самый выгодный",
    },
    "web_quote_single_shop": {
        "uz_latn": "Bir yetkazishda",
        "uz_cyrl": "Бир етказишда",
        "ru": "Одной доставкой",
    },
    "web_quote_fastest": {"uz_latn": "Eng tez", "uz_cyrl": "Энг тез", "ru": "Самый быстрый"},
    "web_quote_premium": {"uz_latn": "Premium", "uz_cyrl": "Премиум", "ru": "Премиум"},
    "web_quote_balanced": {
        "uz_latn": "Muvozanatli",
        "uz_cyrl": "Мувозанатли",
        "ru": "Сбалансированный",
    },
    "web_quote_items_total": {
        "uz_latn": "Mahsulotlar",
        "uz_cyrl": "Маҳсулотлар",
        "ru": "Товары",
    },
    "web_quote_delivery": {
        "uz_latn": "Yetkazib berish",
        "uz_cyrl": "Етказиб бериш",
        "ru": "Доставка",
    },
    "web_quote_grand_total": {"uz_latn": "Jami", "uz_cyrl": "Жами", "ru": "Итого"},
    "web_quote_delivery_unknown": {
        "uz_latn": "Manzil tanlangach",
        "uz_cyrl": "Манзил танлангач",
        "ru": "После выбора адреса",
    },
    "web_quote_delivery_note": {
        "uz_latn": (
            "Yetkazib berish narxi manzilingizga bog'liq va rasmiylashtirishda " "qo'shiladi."
        ),
        "uz_cyrl": ("Етказиб бериш нархи манзилингизга боғлиқ ва расмийлаштиришда " "қўшилади."),
        "ru": ("Стоимость доставки зависит от адреса и добавится при оформлении."),
    },
    "web_quote_select": {"uz_latn": "Buni tanlash", "uz_cyrl": "Буни танлаш", "ru": "Выбрать"},
    "web_quote_pdf": {"uz_latn": "PDF olish", "uz_cyrl": "PDF олиш", "ru": "Скачать PDF"},
    "web_quote_recalc": {
        "uz_latn": "Qayta hisoblash",
        "uz_cyrl": "Қайта ҳисоблаш",
        "ru": "Пересчитать",
    },
    # ── Checkout ──────────────────────────────────────────────────────────
    "web_checkout_title": {
        "uz_latn": "Buyurtmani rasmiylashtirish",
        "uz_cyrl": "Буюртмани расмийлаштириш",
        "ru": "Оформление заказа",
    },
    "web_checkout_phone": {"uz_latn": "Telefon", "uz_cyrl": "Телефон", "ru": "Телефон"},
    "web_checkout_phone_hint": {
        "uz_latn": "Kuryer shu raqamga qo'ng'iroq qiladi.",
        "uz_cyrl": "Курьер шу рақамга қўнғироқ қилади.",
        "ru": "По этому номеру позвонит курьер.",
    },
    "web_checkout_address": {"uz_latn": "Manzil", "uz_cyrl": "Манзил", "ru": "Адрес"},
    "web_checkout_address_new": {
        "uz_latn": "Yangi manzil",
        "uz_cyrl": "Янги манзил",
        "ru": "Новый адрес",
    },
    "web_checkout_detect": {
        "uz_latn": "Joylashuvni aniqlash",
        "uz_cyrl": "Жойлашувни аниқлаш",
        "ru": "Определить местоположение",
    },
    "web_checkout_detecting": {
        "uz_latn": "Aniqlanmoqda…",
        "uz_cyrl": "Аниқланмоқда…",
        "ru": "Определяем…",
    },
    "web_checkout_detect_failed": {
        "uz_latn": "Joylashuvni aniqlay olmadik — manzilni qo'lda yozing.",
        "uz_cyrl": "Жойлашувни аниқлай олмадик — манзилни қўлда ёзинг.",
        "ru": "Не удалось определить местоположение — введите адрес вручную.",
    },
    "web_checkout_address_placeholder": {
        "uz_latn": "Ko'cha, uy, mo'ljal",
        "uz_cyrl": "Кўча, уй, мўлжал",
        "ru": "Улица, дом, ориентир",
    },
    "web_checkout_comment": {"uz_latn": "Izoh", "uz_cyrl": "Изоҳ", "ru": "Комментарий"},
    "web_checkout_comment_hint": {
        "uz_latn": "Ixtiyoriy — qavat, kirish, yetkazish vaqti.",
        "uz_cyrl": "Ихтиёрий — қават, кириш, етказиш вақти.",
        "ru": "Необязательно — этаж, подъезд, время доставки.",
    },
    "web_checkout_confirm": {
        "uz_latn": "Buyurtmani tasdiqlash",
        "uz_cyrl": "Буюртмани тасдиқлаш",
        "ru": "Подтвердить заказ",
    },
    "web_checkout_login_required": {
        "uz_latn": "Buyurtma berish uchun Telegram orqali kiring.",
        "uz_cyrl": "Буюртма бериш учун Telegram орқали киринг.",
        "ru": "Чтобы оформить заказ, войдите через Telegram.",
    },
    "web_checkout_phone_required": {
        "uz_latn": "Telefon raqamini kiriting.",
        "uz_cyrl": "Телефон рақамини киритинг.",
        "ru": "Укажите номер телефона.",
    },
    "web_checkout_address_required": {
        "uz_latn": "Yetkazib berish manzilini kiriting.",
        "uz_cyrl": "Етказиб бериш манзилини киритинг.",
        "ru": "Укажите адрес доставки.",
    },
    "web_checkout_price_changed": {
        "uz_latn": "Narx yangilandi: {total}. Tasdiqlash uchun yana bosing.",
        "uz_cyrl": "Нарх янгиланди: {total}. Тасдиқлаш учун яна босинг.",
        "ru": "Цена обновилась: {total}. Нажмите ещё раз для подтверждения.",
    },
    # ── Orders ────────────────────────────────────────────────────────────
    "web_orders_title": {
        "uz_latn": "Buyurtmalarim",
        "uz_cyrl": "Буюртмаларим",
        "ru": "Мои заказы",
    },
    "web_orders_empty": {
        "uz_latn": "Hali buyurtmalar yo'q.",
        "uz_cyrl": "Ҳали буюртмалар йўқ.",
        "ru": "Заказов пока нет.",
    },
    "web_order_created": {
        "uz_latn": "Buyurtma qabul qilindi",
        "uz_cyrl": "Буюртма қабул қилинди",
        "ru": "Заказ принят",
    },
    "web_order_created_hint": {
        "uz_latn": "Tez orada operator siz bilan bog'lanadi.",
        "uz_cyrl": "Тез орада оператор сиз билан боғланади.",
        "ru": "Скоро с вами свяжется оператор.",
    },
    "web_order_items": {"uz_latn": "Mahsulotlar", "uz_cyrl": "Маҳсулотлар", "ru": "Товары"},
    "web_order_status_new": {"uz_latn": "Yangi", "uz_cyrl": "Янги", "ru": "Новый"},
    "web_order_status_confirmed": {
        "uz_latn": "Tasdiqlangan",
        "uz_cyrl": "Тасдиқланган",
        "ru": "Подтверждён",
    },
    "web_order_status_partially_fulfilled": {
        "uz_latn": "Qisman bajarilgan",
        "uz_cyrl": "Қисман бажарилган",
        "ru": "Частично выполнен",
    },
    "web_order_status_fulfilled": {
        "uz_latn": "Yetkazilgan",
        "uz_cyrl": "Етказилган",
        "ru": "Доставлен",
    },
    "web_order_status_cancelled": {
        "uz_latn": "Bekor qilingan",
        "uz_cyrl": "Бекор қилинган",
        "ru": "Отменён",
    },
    # ── Account ───────────────────────────────────────────────────────────
    "web_account_title": {"uz_latn": "Kabinet", "uz_cyrl": "Кабинет", "ru": "Кабинет"},
    "web_account_pebbles": {"uz_latn": "Toshchalar", "uz_cyrl": "Тошчалар", "ru": "Камешки"},
    "web_account_pebbles_hint": {
        "uz_latn": "Har bir buyurtma uchun to'planadi.",
        "uz_cyrl": "Ҳар бир буюртма учун тўпланади.",
        "ru": "Начисляются за каждый заказ.",
    },
    "web_account_addresses": {
        "uz_latn": "Manzillarim",
        "uz_cyrl": "Манзилларим",
        "ru": "Мои адреса",
    },
    "web_account_addresses_empty": {
        "uz_latn": "Saqlangan manzillar yo'q.",
        "uz_cyrl": "Сақланган манзиллар йўқ.",
        "ru": "Сохранённых адресов нет.",
    },
    "web_account_address_default": {
        "uz_latn": "Asosiy",
        "uz_cyrl": "Асосий",
        "ru": "Основной",
    },
    "web_account_set_default": {
        "uz_latn": "Asosiy qilish",
        "uz_cyrl": "Асосий қилиш",
        "ru": "Сделать основным",
    },
    "web_account_language": {"uz_latn": "Til", "uz_cyrl": "Тил", "ru": "Язык"},
    "web_account_open_bot": {
        "uz_latn": "Telegram botni ochish",
        "uz_cyrl": "Telegram ботни очиш",
        "ru": "Открыть Telegram-бота",
    },
    # ── Login ─────────────────────────────────────────────────────────────
    "web_login_title": {
        "uz_latn": "Telegram orqali kirish",
        "uz_cyrl": "Telegram орқали кириш",
        "ru": "Вход через Telegram",
    },
    "web_login_body": {
        "uz_latn": (
            "Bot bilan bitta hisob — buyurtmalaringiz, manzillaringiz va "
            "toshchalaringiz o'sha joyda qoladi."
        ),
        "uz_cyrl": (
            "Бот билан битта ҳисоб — буюртмаларингиз, манзилларингиз ва "
            "тошчаларингиз ўша жойда қолади."
        ),
        "ru": ("Один аккаунт с ботом — ваши заказы, адреса и камешки остаются на месте."),
    },
    "web_login_unavailable": {
        "uz_latn": "Telegram orqali kirish hozircha sozlanmagan. Botdan foydalaning.",
        "uz_cyrl": "Telegram орқали кириш ҳозирча созланмаган. Ботдан фойдаланинг.",
        "ru": "Вход через Telegram пока не настроен. Воспользуйтесь ботом.",
    },
    "web_login_failed": {
        "uz_latn": "Kirish amalga oshmadi. Qayta urinib ko'ring.",
        "uz_cyrl": "Кириш амалга ошмади. Қайта уриниб кўринг.",
        "ru": "Не удалось войти. Попробуйте ещё раз.",
    },
    "web_login_blocked": {
        "uz_latn": "Bu hisob bloklangan.",
        "uz_cyrl": "Бу ҳисоб блокланган.",
        "ru": "Этот аккаунт заблокирован.",
    },
    # ── Shop portal ───────────────────────────────────────────────────────
    "web_shop_title": {
        "uz_latn": "Do'kon paneli",
        "uz_cyrl": "Дўкон панели",
        "ru": "Панель магазина",
    },
    "web_shop_none": {
        "uz_latn": "Sizga biriktirilgan do'kon topilmadi.",
        "uz_cyrl": "Сизга бириктирилган дўкон топилмади.",
        "ru": "К вам не привязан ни один магазин.",
    },
    "web_shop_products": {
        "uz_latn": "Mahsulotlarim",
        "uz_cyrl": "Маҳсулотларим",
        "ru": "Мои товары",
    },
    "web_shop_orders": {
        "uz_latn": "Buyurtmalar",
        "uz_cyrl": "Буюртмалар",
        "ru": "Заказы",
    },
    "web_shop_delivery": {
        "uz_latn": "Yetkazib berish shartlari",
        "uz_cyrl": "Етказиб бериш шартлари",
        "ru": "Условия доставки",
    },
    "web_shop_import": {
        "uz_latn": "Narxlarni yuklash",
        "uz_cyrl": "Нархларни юклаш",
        "ru": "Загрузка цен",
    },
    "web_shop_price": {"uz_latn": "Narx", "uz_cyrl": "Нарх", "ru": "Цена"},
    "web_shop_stock": {"uz_latn": "Mavjudlik", "uz_cyrl": "Мавжудлик", "ru": "Наличие"},
    "web_shop_stock_in_stock": {"uz_latn": "Bor", "uz_cyrl": "Бор", "ru": "В наличии"},
    "web_shop_stock_low": {"uz_latn": "Kam qoldi", "uz_cyrl": "Кам қолди", "ru": "Мало"},
    "web_shop_stock_on_order": {
        "uz_latn": "Buyurtma asosida",
        "uz_cyrl": "Буюртма асосида",
        "ru": "Под заказ",
    },
    "web_shop_stock_out": {"uz_latn": "Yo'q", "uz_cyrl": "Йўқ", "ru": "Нет"},
    "web_shop_updated": {
        "uz_latn": "Yangilandi",
        "uz_cyrl": "Янгиланди",
        "ru": "Обновлено",
    },
    "web_shop_no_products": {
        "uz_latn": "Hali mahsulot qo'shilmagan.",
        "uz_cyrl": "Ҳали маҳсулот қўшилмаган.",
        "ru": "Товары ещё не добавлены.",
    },
    "web_shop_no_orders": {
        "uz_latn": "Yangi buyurtmalar yo'q.",
        "uz_cyrl": "Янги буюртмалар йўқ.",
        "ru": "Новых заказов нет.",
    },
    "web_shop_accept": {"uz_latn": "Qabul qilish", "uz_cyrl": "Қабул қилиш", "ru": "Принять"},
    "web_shop_reject": {"uz_latn": "Rad etish", "uz_cyrl": "Рад этиш", "ru": "Отклонить"},
    "web_shop_response_pending": {
        "uz_latn": "Javob kutilmoqda",
        "uz_cyrl": "Жавоб кутилмоқда",
        "ru": "Ожидает ответа",
    },
    "web_shop_response_accepted": {
        "uz_latn": "Qabul qilingan",
        "uz_cyrl": "Қабул қилинган",
        "ru": "Принят",
    },
    "web_shop_response_rejected": {
        "uz_latn": "Rad etilgan",
        "uz_cyrl": "Рад этилган",
        "ru": "Отклонён",
    },
    "web_shop_rule_district": {"uz_latn": "Tuman", "uz_cyrl": "Туман", "ru": "Район"},
    "web_shop_rule_all_districts": {
        "uz_latn": "Barcha tumanlar",
        "uz_cyrl": "Барча туманлар",
        "ru": "Все районы",
    },
    "web_shop_rule_fee": {
        "uz_latn": "Yetkazish narxi",
        "uz_cyrl": "Етказиш нархи",
        "ru": "Стоимость доставки",
    },
    "web_shop_rule_free_above": {
        "uz_latn": "Shu summadan bepul",
        "uz_cyrl": "Шу суммадан бепул",
        "ru": "Бесплатно от суммы",
    },
    "web_shop_rule_min_order": {
        "uz_latn": "Eng kam buyurtma",
        "uz_cyrl": "Энг кам буюртма",
        "ru": "Минимальный заказ",
    },
    "web_shop_rule_eta": {
        "uz_latn": "Yetkazish (soat)",
        "uz_cyrl": "Етказиш (соат)",
        "ru": "Доставка (часы)",
    },
    "web_shop_rule_none": {
        "uz_latn": "Shartlar kiritilmagan.",
        "uz_cyrl": "Шартлар киритилмаган.",
        "ru": "Условия не заданы.",
    },
    "web_shop_upload_hint": {
        "uz_latn": "Excel yoki CSV fayl yuklang. Tasdiqlamaguningizcha narxlar o'zgarmaydi.",
        "uz_cyrl": "Excel ёки CSV файл юкланг. Тасдиқламагунингизча нархлар ўзгармайди.",
        "ru": "Загрузите файл Excel или CSV. До подтверждения цены не изменятся.",
    },
    "web_shop_upload": {"uz_latn": "Yuklash", "uz_cyrl": "Юклаш", "ru": "Загрузить"},
    "web_shop_import_total": {
        "uz_latn": "Jami qatorlar",
        "uz_cyrl": "Жами қаторлар",
        "ru": "Всего строк",
    },
    "web_shop_import_matched": {
        "uz_latn": "Avtomatik moslashtirildi",
        "uz_cyrl": "Автоматик мослаштирилди",
        "ru": "Сопоставлено автоматически",
    },
    "web_shop_import_review": {
        "uz_latn": "Tasdiqlash kutmoqda",
        "uz_cyrl": "Тасдиқлаш кутмоқда",
        "ru": "Ожидает проверки",
    },
    "web_shop_import_skipped": {
        "uz_latn": "O'tkazib yuborilgan",
        "uz_cyrl": "Ўтказиб юборилган",
        "ru": "Пропущено",
    },
    "web_shop_import_apply": {
        "uz_latn": "Narxlarni qo'llash",
        "uz_cyrl": "Нархларни қўллаш",
        "ru": "Применить цены",
    },
    "web_shop_import_cancel": {
        "uz_latn": "Bekor qilish",
        "uz_cyrl": "Бекор қилиш",
        "ru": "Отменить",
    },
    "web_shop_import_applied": {
        "uz_latn": "{count} ta narx yangilandi.",
        "uz_cyrl": "{count} та нарх янгиланди.",
        "ru": "Обновлено цен: {count}.",
    },
    "web_shop_import_skip_row": {
        "uz_latn": "O'tkazib yuborish",
        "uz_cyrl": "Ўтказиб юбориш",
        "ru": "Пропустить",
    },
    "web_shop_import_bad_file": {
        "uz_latn": "Faylni o'qib bo'lmadi. Excel (.xlsx) yoki CSV yuboring.",
        "uz_cyrl": "Файлни ўқиб бўлмади. Excel (.xlsx) ёки CSV юборинг.",
        "ru": "Не удалось прочитать файл. Отправьте Excel (.xlsx) или CSV.",
    },
    "web_shop_import_too_big": {
        "uz_latn": "Fayl juda katta.",
        "uz_cyrl": "Файл жуда катта.",
        "ru": "Файл слишком большой.",
    },
}


def t(key: str, lang: str = "uz_latn", **kwargs: Any) -> str:
    """Retrieve localized message string by key, formatted with kwargs."""
    if lang not in ("uz_latn", "uz_cyrl", "ru"):
        lang = "uz_latn"

    entry = MESSAGES.get(key)
    if not entry:
        return key

    template = entry.get(lang) or entry.get("uz_latn") or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    return template
