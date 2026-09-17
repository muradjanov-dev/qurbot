"""Opt-in real model evaluation on staging, never a production database.

Supply only the API key on stdin, never argv. Mount a persistent shared budget
ledger and explicitly set AGENT_EVALUATION_BUDGET_PATH. This script cannot place
orders; only read-only catalogue and approved-policy tools are enabled.
"""

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models.ops import LLMCall
from app.db.models.user import User
from app.db.session import async_session_factory, engine
from app.services.sales_agent import AgentCart, DbAgentTools, SalesAgent


class ReadOnlyTools:
    def __init__(self, delegate: DbAgentTools) -> None:
        self.delegate = delegate
        self.calls: list[dict[str, Any]] = []

    async def run(self, name: str, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        if name not in {"search_products", "get_knowledge"}:
            return {"error": "Read-only evaluation: clarify needs; no cart or order mutation."}
        result = await self.delegate.run(name, args, cart)
        self.calls.append({"name": name, "products": len(result.get("products", []))})
        return result


async def run() -> dict[str, Any]:
    if settings.app_env != "staging" or not settings.agent_evaluation_budget_path:
        raise RuntimeError("requires staging and a persistent evaluation budget path")
    key = sys.stdin.readline().strip()
    if not key or key.startswith("placeholder"):
        raise RuntimeError("API key must be supplied privately on stdin")
    settings.anthropic_api_key = key
    settings.agent_enabled = True
    settings.agent_max_tokens = 600
    settings.agent_max_tool_rounds = 2
    settings.agent_timeout_seconds = 30
    results = []
    async with async_session_factory() as session:
        before = await session.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)))
        user = User(tg_id=-900000002, full_name="Release AI evaluation", lang="uz_latn")
        session.add(user)
        await session.flush()
        for lang, prompt in [
            ("uz_latn", "12 mm fanera qidiryapman. Katalogdan 2 ta variant topib bering."),
            ("uz_cyrl", "12 мм фанера керак. Каталогдан 2 та вариант топиб беринг."),
            ("ru", "Нужна фанера 12 мм. Найдите 2 варианта в каталоге."),
        ]:
            user.lang = lang
            tools = ReadOnlyTools(DbAgentTools(session, user))
            agent = SalesAgent(session, tools)
            try:
                reply = await agent.reply(prompt, lang, AgentCart())
            finally:
                await agent.client.close()
            results.append(
                {"lang": lang, "answered": bool(reply), "tools": tools.calls, "reply": reply}
            )
        after = await session.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0)))
        actual = Decimal(after or 0) - Decimal(before or 0)
        await session.rollback()
    await engine.dispose()
    ledger = json.loads(Path(settings.agent_evaluation_budget_path).read_text())
    return {"results": results, "estimated_usage_usd": str(actual), "ledger": ledger}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False))
