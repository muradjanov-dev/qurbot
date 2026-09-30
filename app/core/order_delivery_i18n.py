"""Localized copy for the durable order delivery notification outbox."""

ORDER_DELIVERY_MESSAGES: dict[str, dict[str, str]] = {
    "delivery_status_new": {
        "uz_latn": "Admin tasdig‘ini kutmoqda",
        "uz_cyrl": "Администратор тасдиғини кутмоқда",
        "ru": "Ожидает подтверждения администратора",
    },
    "delivery_status_confirmed": {
        "uz_latn": "Qabul qilindi",
        "uz_cyrl": "Қабул қилинди",
        "ru": "Принят",
    },
    "delivery_status_collecting": {
        "uz_latn": "Mahsulotlar yig‘ilmoqda",
        "uz_cyrl": "Маҳсулотлар йиғилмоқда",
        "ru": "Товары собираются",
    },
    "delivery_status_in_transit": {
        "uz_latn": "Yetkazish uchun yo‘lga chiqdi",
        "uz_cyrl": "Етказиш учун йўлга чиқди",
        "ru": "Передан в доставку",
    },
    "delivery_status_fulfilled": {
        "uz_latn": "Yetkazildi",
        "uz_cyrl": "Етказилди",
        "ru": "Доставлен",
    },
    "delivery_status_cancelled": {
        "uz_latn": "Bekor qilindi",
        "uz_cyrl": "Бекор қилинди",
        "ru": "Отменён",
    },
    "delivery_status_partially_fulfilled": {
        "uz_latn": "Qisman bajarilgan",
        "uz_cyrl": "Қисман бажарилган",
        "ru": "Выполнен частично",
    },
    "delivery_courier_vehicle_label": {
        "uz_latn": "Transport",
        "uz_cyrl": "Транспорт",
        "ru": "Транспорт",
    },
    "delivery_notification_admin_order_created": {
        "uz_latn": (
            "📦 <b>Yangi buyurtma #{order_id}</b>{channel}\n\n"
            "👤 Mijoz: {customer_name}\n📞 Tel: {phone}\n📍 Manzil: {address}\n"
            "{comment_line}\n{items_block}\n{totals_block}{order_link}"
        ),
        "uz_cyrl": (
            "📦 <b>Янги буюртма #{order_id}</b>{channel}\n\n"
            "👤 Мижоз: {customer_name}\n📞 Тел: {phone}\n📍 Манзил: {address}\n"
            "{comment_line}\n{items_block}\n{totals_block}{order_link}"
        ),
        "ru": (
            "📦 <b>Новый заказ #{order_id}</b>{channel}\n\n"
            "👤 Клиент: {customer_name}\n📞 Телефон: {phone}\n📍 Адрес: {address}\n"
            "{comment_line}\n{items_block}\n{totals_block}{order_link}"
        ),
    },
    "delivery_notification_admin_order_summary": {
        "uz_latn": (
            "📦 <b>Yangi buyurtma #{order_id}</b>\n" "{items_summary}\n{totals_block}{order_link}"
        ),
        "uz_cyrl": (
            "📦 <b>Янги буюртма #{order_id}</b>\n" "{items_summary}\n{totals_block}{order_link}"
        ),
        "ru": ("📦 <b>Новый заказ #{order_id}</b>\n" "{items_summary}\n{totals_block}{order_link}"),
    },
    "delivery_notification_admin_open_order": {
        "uz_latn": "Buyurtmani ochish",
        "uz_cyrl": "Буюртмани очиш",
        "ru": "Открыть заказ",
    },
    "delivery_admin_confirm_order_button": {
        "uz_latn": "✅ Buyurtmani tasdiqlash",
        "uz_cyrl": "✅ Буюртмани тасдиқлаш",
        "ru": "✅ Подтвердить заказ",
    },
    "delivery_admin_cancel_order_button": {
        "uz_latn": "❌ Buyurtmani bekor qilish",
        "uz_cyrl": "❌ Буюртмани бекор қилиш",
        "ru": "❌ Отменить заказ",
    },
    "delivery_admin_accept_order_button": {
        "uz_latn": "✅ Qabul qilish",
        "uz_cyrl": "✅ Қабул қилиш",
        "ru": "✅ Принять",
    },
    "delivery_admin_reject_order_button": {
        "uz_latn": "❌ Rad etish",
        "uz_cyrl": "❌ Рад этиш",
        "ru": "❌ Отклонить",
    },
    "delivery_admin_cancel_reason_hint": {
        "uz_latn": "Bekor qilish sababini buyurtma sahifasida kiriting.",
        "uz_cyrl": "Бекор қилиш сабабини буюртма саҳифасида киритинг.",
        "ru": "Укажите причину отмены на странице заказа.",
    },
    "delivery_admin_cancel_reason_link": {
        "uz_latn": "❌ Buyurtma #{order_id}ni bekor qilish uchun sababni kiriting: {url}",
        "uz_cyrl": "❌ Буюртма #{order_id}ни бекор қилиш учун сабабни киритинг: {url}",
        "ru": "❌ Чтобы отменить заказ #{order_id}, укажите причину на странице заказа: {url}",
    },
    "delivery_admin_order_stale": {
        "uz_latn": "Buyurtma yangilandi; joriy holatni panelda tekshiring.",
        "uz_cyrl": "Буюртма янгиланди; жорий ҳолатни панелда текширинг.",
        "ru": "Заказ обновлён. Проверьте его текущее состояние в панели.",
    },
    "delivery_admin_order_confirmed_feedback": {
        "uz_latn": "✅ Buyurtma #{order_id} tasdiqlandi.",
        "uz_cyrl": "✅ Буюртма #{order_id} тасдиқланди.",
        "ru": "✅ Заказ #{order_id} подтверждён.",
    },
    "delivery_notification_admin_channel_web": {
        "uz_latn": " (sayt)",
        "uz_cyrl": " (сайт)",
        "ru": " (сайт)",
    },
    "delivery_notification_admin_comment": {
        "uz_latn": "💬 Izoh: {comment}",
        "uz_cyrl": "💬 Изоҳ: {comment}",
        "ru": "💬 Комментарий: {comment}",
    },
    "delivery_notification_admin_item_line": {
        "uz_latn": "   • {product} × {qty} {unit} — {line_total} so‘m",
        "uz_cyrl": "   • {product} × {qty} {unit} — {line_total} сўм",
        "ru": "   • {product} × {qty} {unit} — {line_total} сум",
    },
    "delivery_notification_admin_items_truncated": {
        "uz_latn": "… qolgan mahsulotlar buyurtma sahifasida",
        "uz_cyrl": "… қолган маҳсулотлар буюртма саҳифасида",
        "ru": "… остальные товары доступны на странице заказа",
    },
    "delivery_notification_admin_group_total": {
        "uz_latn": "<i>   Jami: {subtotal} + dostavka {delivery} so‘m</i>",
        "uz_cyrl": "<i>   Жами: {subtotal} + доставка {delivery} сўм</i>",
        "ru": "<i>   Итого: {subtotal} + доставка {delivery} сум</i>",
    },
    "delivery_notification_admin_totals": {
        "uz_latn": (
            "Mahsulotlar: {items_total} so‘m\nDostavka: {delivery_total} so‘m\n"
            "<b>JAMI: {total} so‘m</b>"
        ),
        "uz_cyrl": (
            "Маҳсулотлар: {items_total} сўм\nДоставка: {delivery_total} сўм\n"
            "<b>ЖАМИ: {total} сўм</b>"
        ),
        "ru": (
            "Товары: {items_total} сум\nДоставка: {delivery_total} сум\n"
            "<b>ИТОГО: {total} сум</b>"
        ),
    },
    "delivery_notification_customer_order_ack": {
        "uz_latn": ("✅ Buyurtmangiz <b>#{order_id}</b> olindi.\n" "Holati: <b>{status}</b>."),
        "uz_cyrl": ("✅ Буюртмангиз <b>#{order_id}</b> олинди.\n" "Ҳолати: <b>{status}</b>."),
        "ru": ("✅ Ваш заказ <b>#{order_id}</b> получен.\n" "Статус: <b>{status}</b>."),
    },
    "delivery_notification_customer_status": {
        "uz_latn": "📦 Buyurtma <b>#{order_id}</b> holati: <b>{status}</b>.",
        "uz_cyrl": "📦 Буюртма <b>#{order_id}</b> ҳолати: <b>{status}</b>.",
        "ru": "📦 Статус заказа <b>#{order_id}</b>: <b>{status}</b>.",
    },
    "delivery_notification_customer_departure": {
        "uz_latn": (
            "🚚 Buyurtma <b>#{order_id}</b> yo‘lga chiqdi.\n"
            "Kuryer: {courier_name}\nTelefon: {courier_phone}{vehicle_line}"
        ),
        "uz_cyrl": (
            "🚚 Буюртма <b>#{order_id}</b> йўлга чиқди.\n"
            "Курьер: {courier_name}\nТелефон: {courier_phone}{vehicle_line}"
        ),
        "ru": (
            "🚚 Заказ <b>#{order_id}</b> отправлен.\n"
            "Курьер: {courier_name}\nТелефон: {courier_phone}{vehicle_line}"
        ),
    },
    "delivery_notification_customer_cancelled": {
        "uz_latn": ("❌ Buyurtma <b>#{order_id}</b> bekor qilindi.\nSabab: {reason}"),
        "uz_cyrl": ("❌ Буюртма <b>#{order_id}</b> бекор қилинди.\nСабаб: {reason}"),
        "ru": "❌ Заказ <b>#{order_id}</b> отменён.\nПричина: {reason}",
    },
    "delivery_notification_customer_correction": {
        "uz_latn": ("ℹ️ Buyurtma <b>#{order_id}</b> holati tuzatildi: <b>{status}</b>."),
        "uz_cyrl": ("ℹ️ Буюртма <b>#{order_id}</b> ҳолати тузатилди: <b>{status}</b>."),
        "ru": ("ℹ️ Статус заказа <b>#{order_id}</b> исправлен: <b>{status}</b>."),
    },
    "delivery_notification_customer_courier_contact": {
        "uz_latn": (
            "🚚 Buyurtma <b>#{order_id}</b> kuryeri yangilandi.\n"
            "Kuryer: {courier_name}\nTelefon: {courier_phone}"
        ),
        "uz_cyrl": (
            "🚚 Буюртма <b>#{order_id}</b> курьери янгиланди.\n"
            "Курьер: {courier_name}\nТелефон: {courier_phone}"
        ),
        "ru": (
            "🚚 Курьер заказа <b>#{order_id}</b> обновлён.\n"
            "Курьер: {courier_name}\nТелефон: {courier_phone}"
        ),
    },
}
