"""What the chat does when the model cannot answer.

A failed model call used to end the conversation: the customer got "the AI
could not answer" and nothing else -- no products, no buttons, no way forward --
while the admins were told nothing at all. Yet everything the bot did before
the agent existed still works without it. This module reaches for that: the
deterministic catalogue search, returned as the same product cards the agent's
own answers carry, so the existing selection and quantity keyboards apply
unchanged and the customer can still fill a basket and order.

Nothing here calls a model, and nothing here can fail the caller: a fallback
that raises would replace one silent dead end with another.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.deploy_notify import notify_admins
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.ops import Event
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.db.session import async_session_factory

logger = get_logger(__name__)

AI_OUTAGE_EVENT = "chat_ai_outage_warning"


async def deterministic_reply(
    user_id: int, text: str, lang: str
) -> tuple[str, list[dict[str, Any]]]:
    """Answer one message from the catalogue alone.

    Returns the reply and the product cards to attach. The cards are built by
    the agent's own `search_products` tool, which is a read-only catalogue
    query -- reusing it means the fallback and the AI path produce cards of
    exactly the same shape, so one set of keyboards serves both.
    """
    try:
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                return t("chat_ai_unavailable", lang=lang), []
            from app.services.sales_agent import AgentCart, DbAgentTools

            found = await DbAgentTools(session, user).run(
                "search_products", {"query": text}, AgentCart()
            )
            products = found.get("products", [])[:3]
            await session.rollback()
    except Exception:
        # The catalogue is the fallback; if it is also down, say the honest
        # thing rather than propagate into the worker's error handling.
        logger.warning("ai_fallback_search_failed", exc_info=True)
        return t("chat_ai_unavailable", lang=lang), []

    if not products:
        return (
            t("web_chat_ai_fallback_none", lang=lang, phone=settings.support_phone_text),
            [],
        )
    listed = "\n".join(
        f"{index}. {product['name']}"
        + (
            f" — {product['price_from_uzs']} {t('web_currency', lang=lang)}"
            if product.get("price_from_uzs")
            else ""
        )
        for index, product in enumerate(products, start=1)
    )
    return f"{t('web_chat_ai_fallback_found', lang=lang)}\n\n{listed}", products


async def warn_admins_of_ai_outage(error: str) -> bool:
    """Tell the admins the assistant is failing -- once, not once per customer.

    An outage makes every message fail at the same moment, so a per-message
    alert would bury the operator inbox exactly when the operators are most
    needed. Deliberately rate-limited the same way the budget warning is.
    """
    if not settings.telegram_notifications_enabled:
        return False
    try:
        async with async_session_factory() as session:
            since = datetime.now(UTC) - timedelta(minutes=settings.ai_outage_alert_interval_minutes)
            already = await session.scalar(
                select(Event.id)
                .where(Event.name == AI_OUTAGE_EVENT, Event.created_at >= since)
                .limit(1)
            )
            if already is not None:
                return False
            await OpsRepository(session).log_event(name=AI_OUTAGE_EVENT, props={"error": error})
            await session.commit()

        from app.bot.dispatcher import create_bot

        bot = create_bot()
        try:
            await notify_admins(
                bot,
                "⚠️ <b>AI yordamchi javob bera olmayapti</b>\n\n"
                f"Sabab: <code>{error}</code>\n\n"
                "Mijozlar hozir katalog qidiruvi va tugmalar bilan ishlayapti — "
                "bot to'xtagani yo'q, faqat AI javoblari yo'q. Buyurtmalar odatdagidek "
                "keladi.\n\n"
                "Tekshiring: /admin/llm-cost va worker loglari.",
            )
        finally:
            await bot.session.close()
        logger.warning("ai_outage_warning_sent error=%s", error)
        return True
    except Exception:
        logger.exception("ai outage warning failed")
        return False
