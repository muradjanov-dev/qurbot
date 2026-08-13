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
            "<i>500 dona g'isht, 10 qop cement m400, 3 quti plitka 30x30</i>"
        ),
        "uz_cyrl": (
            "Хуш келибсиз! Энди сиз қурилиш материаллари рўйхатини эркин матн "
            "шаклида юборишингиз мумкин. Масалан:\n\n"
            "<i>500 дона ғишт, 10 қоп цемент м400, 3 қути плитка 30х30</i>"
        ),
        "ru": (
            "Добро пожаловать! Теперь вы можете отправить список стройматериалов "
            "простым текстом. Например:\n\n"
            "<i>500 шт кирпич, 10 мешков цемент м400, 3 коробки плитка 30х30</i>"
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
    "menu_price_check": {
        "uz_latn": "🔍 Mahsulot narxi",
        "uz_cyrl": "🔍 Маҳсулот нархи",
        "ru": "🔍 Цены на товары",
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
        "uz_latn": "🚚 Yetkazish: {eta} soat ichida",
        "uz_cyrl": "🚚 Етказиш: {eta} соат ичида",
        "ru": "🚚 Доставка: в течение {eta} ч.",
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
    "not_shop_owner": {
        "uz_latn": "Siz do'kon egasi sifatida ro'yxatdan o'tmagansiz.",
        "uz_cyrl": "Сиз дўкон эгаси сифатида рўйхатдан ўтмагансиз.",
        "ru": "Вы не зарегистрированы как владелец магазина.",
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
