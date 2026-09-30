"""Copy for the one-shop delivery workspace, separate from generic admin UI."""

from __future__ import annotations

_LANGS = ("uz_latn", "uz_cyrl", "ru")

_LABELS: dict[str, tuple[str, str, str]] = {
    "orders_title": (
        "Yetkazib berish buyurtmalari",
        "Етказиб бериш буюртмалари",
        "Заказы на доставку",
    ),
    "orders_hint": (
        "Buyurtmani qidiring, holatini yangilang va yetkazib berishni boshqaring.",
        "Буюртмани қидиринг, ҳолатини янгиланг ва етказиб беришни бошқаринг.",
        "Находите заказы, меняйте статус и управляйте доставкой.",
    ),
    "search": ("Qidirish", "Қидириш", "Поиск"),
    "search_placeholder": (
        "Buyurtma raqami, mijoz, telefon yoki manzil",
        "Буюртма рақами, мижоз, телефон ёки манзил",
        "Номер заказа, клиент, телефон или адрес",
    ),
    "status_filter": ("Holat", "Ҳолат", "Статус"),
    "all_statuses": ("Barcha holatlar", "Барча ҳолатлар", "Все статусы"),
    "problem_only": ("Muammoli buyurtmalar", "Муаммоли буюртмалар", "Проблемные заказы"),
    "apply_filter": ("Ko‘rsatish", "Кўрсатиш", "Показать"),
    "order_count": ("Buyurtmalar: {count}", "Буюртмалар: {count}", "Заказов: {count}"),
    "no_orders": ("Buyurtmalar topilmadi.", "Буюртмалар топилмади.", "Заказы не найдены."),
    "read_only_badge": (
        "Tarixiy · faqat ko‘rish",
        "Тарихий · фақат кўриш",
        "Исторический · только просмотр",
    ),
    "historical_read_only": (
        "Bu buyurtma joriy do‘konga tegishli emas. Saqlangan ma’lumotlar ko‘rsatiladi, "
        "ish jarayonini o‘zgartirib bo‘lmaydi.",
        "Бу буюртма жорий дўконга тегишли эмас. Сақланган маълумотлар кўрсатилади, "
        "иш жараёнини ўзгартириб бўлмайди.",
        "Этот заказ не относится к текущему магазину. Сохранённые данные доступны для "
        "просмотра, менять процесс нельзя.",
    ),
    "previous": ("Oldingi", "Олдинги", "Назад"),
    "next": ("Keyingi", "Кейинги", "Далее"),
    "order": ("Buyurtma", "Буюртма", "Заказ"),
    "customer": ("Mijoz", "Мижоз", "Клиент"),
    "telegram_unlinked": (
        "Telegram akkaunti ulanmagan",
        "Telegram аккаунти уланмаган",
        "Telegram-аккаунт не подключён",
    ),
    "phone": ("Telefon", "Телефон", "Телефон"),
    "address": ("Yetkazish manzili", "Етказиш манзили", "Адрес доставки"),
    "customer_comment": ("Mijoz izohi", "Мижоз изоҳи", "Комментарий клиента"),
    "items": ("Buyurtma tarkibi", "Буюртма таркиби", "Состав заказа"),
    "quoted_total": ("Buyurtma summasi", "Буюртма суммаси", "Сумма заказа"),
    "created": ("Yaratilgan", "Яратилган", "Создан"),
    "updated": ("Oxirgi yangilanish", "Охирги янгиланиш", "Последнее обновление"),
    "delivery_management": ("Yetkazib berish", "Етказиб бериш", "Доставка"),
    "courier": ("Kuryer", "Курьер", "Курьер"),
    "courier_name": ("Kuryer ismi", "Курьер исми", "Имя курьера"),
    "courier_phone": ("Kuryer telefoni", "Курьер телефони", "Телефон курьера"),
    "vehicle": ("Transport (ixtiyoriy)", "Транспорт (ихтиёрий)", "Транспорт (необязательно)"),
    "internal_cost": (
        "Ichki xarajat, so‘m (ixtiyoriy)",
        "Ички харажат, сўм (ихтиёрий)",
        "Внутренний расход, сум (необязательно)",
    ),
    "courier_required_hint": (
        "“Yo‘lda” holatidan oldin kuryer ismi va telefoni saqlanishi kerak.",
        "«Йўлда» ҳолатидан олдин курьер исми ва телефони сақланиши керак.",
        "Перед статусом «В пути» сохраните имя и телефон курьера.",
    ),
    "courier_required": (
        "“Yo‘lda” yoki “Yetkazildi” holatidan oldin kuryer ismi va telefonini saqlang.",
        "«Йўлда» ёки «Етказилди» ҳолатидан олдин курьер исми ва телефонини сақланг.",
        "Перед статусом «В пути» или «Доставлен» сохраните имя и телефон курьера.",
    ),
    "save_courier": ("Kuryerni saqlash", "Курьерни сақлаш", "Сохранить курьера"),
    "delivery_note": (
        "Ichki yetkazish qaydi",
        "Ички етказиш қайди",
        "Внутренняя заметка о доставке",
    ),
    "problem_marker": ("Muammo bor", "Муаммо бор", "Есть проблема"),
    "save_note": ("Qaydni saqlash", "Қайдни сақлаш", "Сохранить заметку"),
    "change_status": ("Holatni yangilash", "Ҳолатни янгилаш", "Изменить статус"),
    "target_status": ("Yangi holat", "Янги ҳолат", "Новый статус"),
    "reason": ("Sabab", "Сабаб", "Причина"),
    "cancel_reason_required": (
        "Bekor qilish sababini kiriting.",
        "Бекор қилиш сабабини киритинг.",
        "Укажите причину отмены.",
    ),
    "save_status": ("Holatni saqlash", "Ҳолатни сақлаш", "Сохранить статус"),
    "correction": ("Holatni tuzatish", "Ҳолатни тузатиш", "Исправить статус"),
    "correction_hint": (
        "Yakunlangan yoki boshqa istalgan holatni tuzatish uchun sabab majburiy.",
        "Якунланган ёки бошқа исталган ҳолатни тузатиш учун сабаб шарт.",
        "Для исправления любого статуса, включая завершённый, укажите причину.",
    ),
    "save_correction": ("Tuzatishni saqlash", "Тузатишни сақлаш", "Сохранить исправление"),
    "timeline": ("Buyurtma tarixi", "Буюртма тарихи", "История заказа"),
    "details": ("Batafsil", "Батафсил", "Подробнее"),
    "notifications": ("Bildirishnomalar", "Билдиришномалар", "Уведомления"),
    "notification_status": ("Holat", "Ҳолат", "Статус"),
    "notification_attention": (
        "Qayta yuborish kerak",
        "Қайта юбориш керак",
        "Требуется повторная отправка",
    ),
    "notification_queued_label": ("Navbatda", "Навбатда", "В очереди"),
    "notification_sent_label": ("Yuborildi", "Юборилди", "Отправлено"),
    "notification_failed_label": ("Xato", "Хато", "Ошибка"),
    "notification_channel": ("Kanal", "Канал", "Канал"),
    "notification_recipient": ("Qabul qiluvchi", "Қабул қилувчи", "Получатель"),
    "notification_attempts": ("Urinishlar", "Уринишлар", "Попытки"),
    "notification_order_created": (
        "Yangi buyurtma xabari",
        "Янги буюртма хабари",
        "Сообщение о новом заказе",
    ),
    "notification_customer_ack": (
        "Mijozga qabul xabari",
        "Мижозга қабул хабари",
        "Подтверждение клиенту",
    ),
    "notification_customer_status": (
        "Mijozga holat xabari",
        "Мижозга ҳолат хабари",
        "Статус для клиента",
    ),
    "notification_customer_correction": (
        "Mijozga tuzatish xabari",
        "Мижозга тузатиш хабари",
        "Исправление для клиента",
    ),
    "notification_courier_contact": (
        "Kuryer kontakti xabari",
        "Курьер контакти хабари",
        "Контакт курьера клиенту",
    ),
    "notification_departure": (
        "Yo‘lga chiqish xabari",
        "Йўлга чиқиш хабари",
        "Сообщение об отправке",
    ),
    "notification_admin_location": (
        "Yetkazish manzili pini",
        "Етказиш манзили белгиси",
        "Метка адреса доставки",
    ),
    "notification_error": ("Xatolik", "Хатолик", "Ошибка"),
    "retry_notification": ("Qayta yuborish", "Қайта юбориш", "Повторить отправку"),
    "no_notifications": (
        "Bildirishnoma yozuvlari yo‘q.",
        "Билдиришнома ёзувлари йўқ.",
        "Записей об уведомлениях нет.",
    ),
    "status_saved": ("Buyurtma yangilandi.", "Буюртма янгиланди.", "Заказ обновлён."),
    "courier_saved": (
        "Kuryer ma’lumotlari saqlandi.",
        "Курьер маълумотлари сақланди.",
        "Данные курьера сохранены.",
    ),
    "note_saved": ("Ichki qayd saqlandi.", "Ички қайд сақланди.", "Внутренняя заметка сохранена."),
    "notification_queued": (
        "Bildirishnoma qayta yuborish uchun navbatga qo‘shildi.",
        "Билдиришнома қайта юбориш учун навбатга қўшилди.",
        "Уведомление добавлено в очередь повторной отправки.",
    ),
    "stale_order": (
        "Buyurtma boshqa oynada yangilandi. Joriy ma’lumotlarni ko‘rib, qayta urinib ko‘ring.",
        "Буюртма бошқа ойнада янгиланди. Жорий маълумотларни кўриб, қайта уриниб кўринг.",
        "Заказ изменён в другом окне. Проверьте текущие данные и повторите.",
    ),
    "invalid_transition": (
        "Bu holatga o‘tib bo‘lmaydi. Joriy holat yangilandi.",
        "Бу ҳолатга ўтиб бўлмайди. Жорий ҳолат янгиланди.",
        "Этот переход недоступен. Показан текущий статус.",
    ),
    "terminal_status_help": (
        "Bu yakuniy holat. Zarur tuzatish uchun alohida sabab kiriting.",
        "Бу якуний ҳолат. Зарур тузатиш учун алоҳида сабаб киритинг.",
        "Это конечный статус. Для исправления укажите отдельную причину.",
    ),
    "legacy_status_help": (
        "Bu avvalgi tizimdan qolgan holat. Ish jarayoni uni o‘zgartirmaydi.",
        "Бу аввалги тизимдан қолган ҳолат. Иш жараёни уни ўзгартирмайди.",
        "Это исторический статус. Новый процесс его не изменяет.",
    ),
    "workflow_error": (
        "Buyurtmani yangilab bo‘lmadi. Joriy ma’lumotlar yangilandi.",
        "Буюртмани янгилаб бўлмади. Жорий маълумотлар янгиланди.",
        "Не удалось обновить заказ. Данные обновлены.",
    ),
    "invalid_courier_cost": (
        "Xarajatni musbat butun so‘mda kiriting.",
        "Харажатни мусбат бутун сўмда киритинг.",
        "Введите положительную сумму в целых сумах.",
    ),
    "status_event": ("Holat o‘zgardi", "Ҳолат ўзгарди", "Статус изменён"),
    "status_correction_event": ("Holat tuzatildi", "Ҳолат тузатилди", "Статус исправлен"),
    "courier_event": (
        "Kuryer ma’lumoti yangilandi",
        "Курьер маълумоти янгиланди",
        "Данные курьера обновлены",
    ),
    "note_event": ("Ichki qayd yangilandi", "Ички қайд янгиланди", "Внутренняя заметка обновлена"),
    "problem_event": (
        "Muammo belgisi yangilandi",
        "Муаммо белгиси янгиланди",
        "Обновлена отметка о проблеме",
    ),
    "notification_event": ("Bildirishnoma holati", "Билдиришнома ҳолати", "Статус уведомления"),
    "status_from": ("{status} holatidan", "{status} ҳолатидан", "Из статуса {status}"),
    "status_to": ("{status} holatiga", "{status} ҳолатига", "В статус {status}"),
    "problem_badge": ("Muammo", "Муаммо", "Проблема"),
    "public_delivery": ("Yetkazish holati", "Етказиш ҳолати", "Статус доставки"),
    "driver_contact": ("Kuryer bilan bog‘lanish", "Курьер билан боғланиш", "Связаться с курьером"),
    "no_public_updates": (
        "Hozircha yangilanishlar yo‘q.",
        "Ҳозирча янгиланишлар йўқ.",
        "Обновлений пока нет.",
    ),
}

FULFILLMENT_UI_MESSAGES: dict[str, dict[str, str]] = {
    f"fulfillment_ui_{key}": dict(zip(_LANGS, values, strict=True))
    for key, values in _LABELS.items()
}


def fulfillment_ui_messages(lang: str) -> dict[str, str]:
    """Return fulfillment strings with the template namespace removed."""
    selected = lang if lang in _LANGS else "uz_cyrl"
    return {
        key.removeprefix("fulfillment_ui_"): translations.get(selected, translations["uz_cyrl"])
        for key, translations in FULFILLMENT_UI_MESSAGES.items()
    }
