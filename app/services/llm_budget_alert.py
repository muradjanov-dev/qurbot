"""Tell the admins before the AI goes quiet, not after.

When the daily token budget runs out every LLM stage stops answering, and from
the outside that is indistinguishable from a model with nothing to say: baskets
quietly get worse, nobody is told, and the cause is a number in an environment
variable. So the last stretch of the budget is announced while there is still
room to act on it.

Announced once a day: the check runs on the path of every LLM call, and four
admins do not need one message per basket. The `events` table is the record of
what was already said.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deploy_notify import notify_admins
from app.db.models.ops import Event
from app.db.repositories.ops_repo import OpsRepository

logger = logging.getLogger(__name__)

BUDGET_WARNING_EVENT = "llm_budget_warning"


def _message(used_tokens: int, budget: int) -> str:
    percent = round(used_tokens / budget * 100) if budget else 100
    remaining = max(budget - used_tokens, 0)
    suggested = budget * 3
    return (
        "⚠️ <b>AI limiti tugash arafasida</b>\n\n"
        f"Oxirgi 24 soatdagi sarf: <b>{used_tokens:,} / {budget:,}</b> token ({percent}%).\n"
        f"Qolgani: {remaining:,} token.\n\n"
        "Limit tugasa, bot AI yordamisiz ishlaydi: noaniq qatorlarni o'zi aniqlay "
        "olmaydi va mijozga tanlash uchun ro'yxat beradi. Bot to'xtamaydi, "
        "faqat aniqligi pasayadi.\n\n"
        "<b>Nima qilish kerak:</b>\n"
        "1. Railway → web → Variables → <code>LLM_DAILY_TOKEN_BUDGET</code> "
        f"qiymatini oshiring (masalan <code>{suggested:,}</code>) va Redeploy bosing.\n"
        "2. Yoki kutasiz — limit 24 soat ichida o'zi tiklanadi.\n"
        "3. Sarfni ko'rish: /admin/llm-cost"
    ).replace(",", " ")


async def warn_admins_if_budget_low(session: AsyncSession, used_tokens: int) -> bool:
    """DM the admins once a day when the daily AI budget is nearly spent.

    Returns whether a warning was sent. Never raises: a failed notification
    must not take the LLM call down with it -- the point of this module is to
    make a degradation visible, not to add one.
    """
    budget = settings.llm_daily_token_budget
    if budget <= 0:
        return False
    if used_tokens < budget * settings.llm_budget_warn_ratio:
        return False

    try:
        since = datetime.now(UTC) - timedelta(hours=24)
        already = await session.execute(
            select(Event.id)
            .where(Event.name == BUDGET_WARNING_EVENT, Event.created_at >= since)
            .limit(1)
        )
        if already.scalars().first() is not None:
            return False

        # Imported here rather than at module scope: the dispatcher pulls in the
        # handlers, which pull in the services, which pull in the LLM client
        # that calls this function -- a cycle at import time.
        from app.bot.dispatcher import create_bot

        bot = create_bot()
        try:
            await notify_admins(bot, _message(used_tokens, budget))
        finally:
            await bot.session.close()

        await OpsRepository(session).log_event(
            name=BUDGET_WARNING_EVENT,
            props={"used_tokens": used_tokens, "budget": budget},
        )
        logger.warning("llm_budget_warning_sent used=%d budget=%d", used_tokens, budget)
        return True
    except Exception:
        logger.exception("llm budget warning failed")
        return False
