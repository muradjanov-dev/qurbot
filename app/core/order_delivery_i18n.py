"""Localized copy for the durable order delivery notification outbox."""

ORDER_DELIVERY_MESSAGES: dict[str, dict[str, str]] = {
    "delivery_status_new": {
        "uz_latn": "Yangi",
        "uz_cyrl": "Янги",
        "ru": "Новый",
    },
    "delivery_status_confirmed": {
        "uz_latn": "Tasdiqlandi",
        "uz_cyrl": "Тасдиқланди",
        "ru": "Подтверждён",
    },
    "delivery_status_collecting": {
        "uz_latn": "Yig‘ilmoqda",
        "uz_cyrl": "Йиғилмоқда",
        "ru": "Комплектуется",
    },
    "delivery_status_in_transit": {
        "uz_latn": "Yo‘lda",
        "uz_cyrl": "Йўлда",
        "ru": "В пути",
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
    "delivery_notification_admin_order_created": {
        "uz_latn": (
            "📦 <b>Yangi buyurtma #{order_id}</b>\n"
            "Mijoz: {customer_name}\nTel: {phone}\nManzil: {address}"
        ),
        "uz_cyrl": (
            "📦 <b>Янги буюртма #{order_id}</b>\n"
            "Мижоз: {customer_name}\nТел: {phone}\nМанзил: {address}"
        ),
        "ru": (
            "📦 <b>Новый заказ #{order_id}</b>\n"
            "Клиент: {customer_name}\nТелефон: {phone}\nАдрес: {address}"
        ),
    },
    "delivery_notification_customer_order_ack": {
        "uz_latn": (
            "✅ Buyurtmangiz <b>#{order_id}</b> qabul qilindi.\n"
            "Holati: <b>{status}</b>."
        ),
        "uz_cyrl": (
            "✅ Буюртмангиз <b>#{order_id}</b> қабул қилинди.\n"
            "Ҳолати: <b>{status}</b>."
        ),
        "ru": (
            "✅ Ваш заказ <b>#{order_id}</b> принят.\n"
            "Статус: <b>{status}</b>."
        ),
    },
    "delivery_notification_customer_status": {
        "uz_latn": "📦 Buyurtma <b>#{order_id}</b> holati: <b>{status}</b>.",
        "uz_cyrl": "📦 Буюртма <b>#{order_id}</b> ҳолати: <b>{status}</b>.",
        "ru": "📦 Статус заказа <b>#{order_id}</b>: <b>{status}</b>.",
    },
    "delivery_notification_customer_cancelled": {
        "uz_latn": (
            "❌ Buyurtma <b>#{order_id}</b> bekor qilindi.\nSabab: {reason}"
        ),
        "uz_cyrl": (
            "❌ Буюртма <b>#{order_id}</b> бекор қилинди.\nСабаб: {reason}"
        ),
        "ru": "❌ Заказ <b>#{order_id}</b> отменён.\nПричина: {reason}",
    },
    "delivery_notification_customer_correction": {
        "uz_latn": (
            "ℹ️ Buyurtma <b>#{order_id}</b> holati tuzatildi: <b>{status}</b>.\n"
            "Sabab: {reason}"
        ),
        "uz_cyrl": (
            "ℹ️ Буюртма <b>#{order_id}</b> ҳолати тузатилди: <b>{status}</b>.\n"
            "Сабаб: {reason}"
        ),
        "ru": (
            "ℹ️ Статус заказа <b>#{order_id}</b> исправлен: <b>{status}</b>.\n"
            "Причина: {reason}"
        ),
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
