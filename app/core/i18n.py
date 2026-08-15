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
            "«<b>500 dona g'isht, 10 qop cement m400, 3 quti plitka 30x30</b>»\n\n"
            "Qurilish mollaringizni ro'yxatini yuboring va biz Sizga ularni "
            "topib, jamlab, yetkazib beramiz."
        ),
        "uz_cyrl": (
            "Хуш келибсиз! Энди сиз қурилиш материаллари рўйхатини эркин матн "
            "шаклида юборишингиз мумкин. Масалан:\n\n"
            "«<b>500 дона ғишт, 10 қоп цемент м400, 3 қути плитка 30х30</b>»\n\n"
            "Қурилиш молларингизни рўйхатини юборинг ва биз Сизга уларни "
            "топиб, жамлаб, етказиб берамиз."
        ),
        "ru": (
            "Добро пожаловать! Теперь вы можете отправить список стройматериалов "
            "простым текстом. Например:\n\n"
            "«<b>500 шт кирпич, 10 мешков цемент м400, 3 коробки плитка 30х30</b>»\n\n"
            "Отправьте список стройматериалов, а мы найдём их, "
            "соберём и доставим вам."
        ),
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
    "product_card": {
        "uz_latn": (
            "<b>{name}</b>\n\n"
            "🏷 Brend: {brand}\n"
            "💰 Narx: <b>{min_price} — {max_price} so'm</b>\n"
            "🏪 Do'konlarda: {shops} ta taklif\n"
            "📏 O'lchov: {unit}"
        ),
        "uz_cyrl": (
            "<b>{name}</b>\n\n"
            "🏷 Бренд: {brand}\n"
            "💰 Нарх: <b>{min_price} — {max_price} сўм</b>\n"
            "🏪 Дўконларда: {shops} та таклиф\n"
            "📏 Ўлчов: {unit}"
        ),
        "ru": (
            "<b>{name}</b>\n\n"
            "🏷 Бренд: {brand}\n"
            "💰 Цена: <b>{min_price} — {max_price} сум</b>\n"
            "🏪 В магазинах: {shops} предложений\n"
            "📏 Единица: {unit}"
        ),
    },
    "product_card_no_offers": {
        "uz_latn": "<b>{name}</b>\n\nHozircha do'konlarda mavjud emas.",
        "uz_cyrl": "<b>{name}</b>\n\nҲозирча дўконларда мавжуд эмас.",
        "ru": "<b>{name}</b>\n\nПока нет в наличии в магазинах.",
    },
    "price_browse_choose_category": {
        "uz_latn": "🔍 <b>Mahsulot narxlari</b>\n\nKategoriyani tanlang:",
        "uz_cyrl": "🔍 <b>Маҳсулот нархлари</b>\n\nКатегорияни танланг:",
        "ru": "🔍 <b>Цены на товары</b>\n\nВыберите категорию:",
    },
    "price_browse_empty": {
        "uz_latn": "Bu kategoriyada hozircha narxlar mavjud emas.",
        "uz_cyrl": "Бу категорияда ҳозирча нархлар мавжуд эмас.",
        "ru": "В этой категории пока нет цен.",
    },
    "price_browse_header": {
        "uz_latn": "💰 <b>{category}</b>\n\nBatafsil ko'rish uchun mahsulotni tanlang:",
        "uz_cyrl": "💰 <b>{category}</b>\n\nБатафсил кўриш учун маҳсулотни танланг:",
        "ru": "💰 <b>{category}</b>\n\nВыберите товар, чтобы посмотреть подробнее:",
    },
    "price_browse_hint": {
        "uz_latn": "\n<i>Narxlar — do'konlardagi eng arzon taklif.</i>",
        "uz_cyrl": "\n<i>Нархлар — дўконлардаги энг арзон таклиф.</i>",
        "ru": "\n<i>Цены — самое дешёвое предложение среди магазинов.</i>",
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
    "prompt_send_basket": {
        "uz_latn": (
            "Qurilish mollari ro'yxatini yuboring.\n"
            "Har bir mahsulotni yangi qatordan yoki vergul bilan ajratib yozing:"
        ),
        "uz_cyrl": (
            "Қурилиш моллари рўйхатини юборинг.\n"
            "Ҳар бир маҳсулотни янги қатордан ёки вергул билан ажратиб ёзинг:"
        ),
        "ru": (
            "Отправьте список стройматериалов.\n"
            "Пишите каждый товар с новой строки или через запятую:"
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
            "10 qop sement\n500 dona g'isht\n3 quti plitka 30x30"
        ),
        "uz_cyrl": (
            "Кечирасиз, тушунмадим 🙂\n"
            "QurBot қурилиш моллари нархини ҳисоблайди. Ҳар бир маҳсулотни "
            "янги қатордан, <b>миқдор + бирлик + ном</b> тартибида ёзинг. Масалан:\n\n"
            "10 қоп цемент\n500 дона ғишт\n3 қути плитка 30х30"
        ),
        "ru": (
            "Извините, не понял 🙂\n"
            "QurBot считает цены на стройматериалы. Пишите каждый товар с новой "
            "строки в формате <b>количество + единица + название</b>. Например:\n\n"
            "10 мешков цемент\n500 шт кирпич\n3 коробки плитка 30х30"
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
    "btn_recalculate": {
        "uz_latn": "🔄 Qayta hisoblash",
        "uz_cyrl": "🔄 Қайта ҳисоблаш",
        "ru": "🔄 Пересчитать",
    },
    "quote_header_cheapest": {
        "uz_latn": "💰 <b>ENG TEJAMLI VARIANT</b>",
        "uz_cyrl": "💰 <b>ЭНГ ТЕЖАМЛИ ВАРИАНТ</b>",
        "ru": "💰 <b>САМЫЙ ВЫГОДНЫЙ ВАРИАНТ</b>",
    },
    "quote_header_single_shop": {
        "uz_latn": "🏪 <b>BITTA DO'KONDAN</b>",
        "uz_cyrl": "🏪 <b>БИТТА ДЎКОНДАН</b>",
        "ru": "🏪 <b>ИЗ ОДНОГО МАГАЗИНА</b>",
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
            "Do'kon uchun qo'shimcha izoh yoki istak (ixtiyoriy, 'yo'q' deb yozishingiz mumkin):"
        ),
        "uz_cyrl": "Дўкон учун қўшимча изоҳ ёки истак (ихтиёрий, 'йўқ' деб ёзишингиз мумкин):",
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
            "Do'konlar buyurtmani ko'rib chiqib, tez orada siz bilan bog'lanishadi."
        ),
        "uz_cyrl": (
            "🎉 <b>Буюртмангиз қабул қилинди!</b>\n\n"
            "Буюртма рақами: <b>#{order_id}</b>\n"
            "Жами сумма: <b>{total} сўм</b>\n\n"
            "Дўконлар буюртмани кўриб чиқиб, тез орада сиз билан боғланишади."
        ),
        "ru": (
            "🎉 <b>Ваш заказ успешно оформлен!</b>\n\n"
            "Номер заказа: <b>#{order_id}</b>\n"
            "Сумма к оплате: <b>{total} сум</b>\n\n"
            "Магазины получили заказ и скоро свяжутся с вами."
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
            "Masalan: <code>cement m400 52000</code> yoki <code>g'isht 1400</code>"
        ),
        "uz_cyrl": (
            "Тез нарх янгилаш учун маҳсулот ва нархни юборинг.\n"
            "Масалан: <code>цемент м400 52000</code> ёки <code>ғишт 1400</code>"
        ),
        "ru": (
            "Для быстрого обновления отправьте название и цену.\n"
            "Например: <code>цемент м400 52000</code> или <code>кирпич 1400</code>"
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
        "uz_latn": ("2/7 — Mahsulot nomini yozing.\n" "<i>Masalan: Sement M400 50kg qop</i>"),
        "uz_cyrl": ("2/7 — Маҳсулот номини ёзинг.\n" "<i>Масалан: Sement M400 50kg қоп</i>"),
        "ru": ("2/7 — Напишите название товара.\n" "<i>Например: Цемент М400 мешок 50кг</i>"),
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
            "<i>Masalan: 50 kg lik sement qop uchun — 50</i>"
        ),
        "uz_cyrl": (
            "Битта қадоқ (қоп/қути/рулон) ичида неча <b>{unit}</b> бор?\n"
            "<i>Масалан: 50 кг лик цемент қоп учун — 50</i>"
        ),
        "ru": (
            "Сколько <b>{unit}</b> в одной упаковке (мешок/коробка/рулон)?\n"
            "<i>Например: для мешка цемента 50 кг — 50</i>"
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
