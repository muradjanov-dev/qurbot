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

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.bot.formatters.common import format_uzs
from app.core.config import settings
from app.core.deploy_notify import notify_admins
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.ops import Event
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.db.session import async_session_factory
from app.domain.normalize.text import normalize_query

logger = get_logger(__name__)

AI_OUTAGE_EVENT = "chat_ai_outage_warning"


_FAMILIES = (
    ("fanera", re.compile(r"\bfanera\b")),
    ("osb", re.compile(r"\bosb\b")),
    ("taxta", re.compile(r"\b(?:taxta|doska)\b")),
    ("anker", re.compile(r"\banker\b")),
)
_LIST_INTENT = re.compile(r"\b(?:barcha|hammasi|hamma|royxat|ro'yxat|katalog|variantlar|turlar)\b")
_PURCHASE_INTENT = re.compile(r"\b(?:kerak|olaman|olmoqchi|buyurtma|narx|bormi|bor)\b")
_SHEET_SIZE = re.compile(r"\b(?:\d{3,4}x\d{3,4}|\d[.,]\d{2,3}x\d[.,]\d{2,3})\b")
_THICKNESS = re.compile(r"\b\d+(?:[.,]\d+)?\s*mm\b")
_BOARD_SIZE = re.compile(r"\b\d+(?:[.,]\d+)?x\d+(?:[.,]\d+)?x\d+(?:[.,]\d+)?\b")
_TWO_DIMENSIONS = re.compile(r"\b\d+(?:[.,]\d+)?x\d+(?:[.,]\d+)?\b")


def missing_spec(text: str) -> str | None:
    """One missing physical detail for a broad shopping request, in mention order."""
    normalized = normalize_query(text).text_norm.replace("×", "x").replace("х", "x")
    if _LIST_INTENT.search(normalized):
        return None
    mentions = sorted(
        (match.start(), key, match.end())
        for key, pattern in _FAMILIES
        for match in pattern.finditer(normalized)
    )
    if not mentions:
        return None
    if not _PURCHASE_INTENT.search(text.casefold()) and normalized.strip() not in {
        "fanera",
        "osb",
        "taxta",
        "anker",
        "oq anker",
    }:
        return None
    for index, (start, key, _) in enumerate(mentions):
        segment = normalized[start : mentions[index + 1][0] if index + 1 < len(mentions) else None]
        if key == "fanera":
            if not _THICKNESS.search(segment):
                return "fanera_thickness"
            if not _SHEET_SIZE.search(segment):
                return "fanera_sheet_size"
        elif key == "osb" and not _THICKNESS.search(segment):
            return "osb_thickness"
        elif key == "taxta" and not _BOARD_SIZE.search(segment):
            return "taxta_size"
        elif key == "anker" and not _TWO_DIMENSIONS.search(segment):
            return "anker_size"
    return None


def continue_clarification(query: str, key: str, answer: str) -> str | None:
    """Add one customer's answer to the matching item of a multi-product request."""
    if len(answer) > 120 or len(query) > 700:
        return None
    answer = answer.strip()
    if key.endswith("thickness") and re.fullmatch(r"\d+(?:[.,]\d+)?", answer):
        answer += " mm"
    normalized_answer = normalize_query(answer).text_norm.replace("×", "x").replace("х", "x")
    required = (
        _THICKNESS
        if key.endswith("thickness")
        else _SHEET_SIZE
        if key == "fanera_sheet_size"
        else _BOARD_SIZE
        if key == "taxta_size"
        else _TWO_DIMENSIONS
    )
    if not required.search(normalized_answer):
        return None
    family = key.split("_", 1)[0]
    match = next(
        (m for name, pattern in _FAMILIES if name == family for m in pattern.finditer(query)),
        None,
    )
    if match is None:
        return None
    return f"{query[:match.end()]} {answer}{query[match.end():]}"


def product_queries(text: str) -> list[str]:
    """Search each named product family separately after dimensions are known."""
    normalized = normalize_query(text).text_norm
    matches = sorted(
        (match.start(), key) for key, pattern in _FAMILIES for match in pattern.finditer(normalized)
    )
    if len(matches) < 2:
        return [text]
    return [
        re.sub(
            r"\b(?:va|hamda)\s*$",
            "",
            normalized[start : matches[index + 1][0] if index + 1 < len(matches) else None],
        ).strip()
        for index, (start, _) in enumerate(matches)
    ]


async def deterministic_reply(
    user_id: int, text: str, lang: str
) -> tuple[str, list[dict[str, Any]]]:
    """Answer one message from the catalogue alone.

    Returns the reply and the product cards to attach. The cards are built by
    the agent's own `search_products` tool, which is a read-only catalogue
    query -- reusing it means the fallback and the AI path produce cards of
    exactly the same shape, so one set of keyboards serves both.
    """
    clarification = missing_spec(text)
    if clarification is not None:
        return t(f"sales_clarify_{clarification}", lang=lang), []
    try:
        async with async_session_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                return t("chat_ai_unavailable", lang=lang), []
            from app.services.sales_agent import AgentCart, DbAgentTools

            tools = DbAgentTools(session, user)
            products = []
            seen: set[int] = set()
            groups = []
            for query in product_queries(text):
                found = await tools.run("search_products", {"query": query}, AgentCart())
                groups.append(found.get("products", []))
            for rank in range(settings.agent_search_limit):
                for group in groups:
                    if rank >= len(group):
                        continue
                    product = group[rank]
                    product_id = int(product["id"])
                    if product_id not in seen:
                        seen.add(product_id)
                        products.append(product)
                if len(products) >= settings.agent_search_limit:
                    break
            products = products[: settings.agent_search_limit]
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
            f" — {format_uzs(Decimal(str(product['price_from_uzs'])))} "
            f"{t('currency_suffix', lang=lang)}"
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
