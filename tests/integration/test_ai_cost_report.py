"""End of day, admins get the AI bill: dollars per model and per API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.repositories.ops_repo import OpsRepository
from app.workers.tasks import _ai_cost_report_impl


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


async def _call(
    session: AsyncSession, model: str | None, cost: str, *, cache_hit: bool = False
) -> None:
    await OpsRepository(session).record_llm_call(
        purpose="test",
        prompt_version="v1",
        input_hash="h",
        input_tokens=1000,
        output_tokens=100,
        cost_usd=Decimal(cost),
        latency_ms=1,
        cache_hit=cache_hit,
        model=model,
    )


async def test_report_groups_spend_by_model_and_provider(test_session: AsyncSession) -> None:
    await _call(test_session, "claude-opus-5", "0.40")
    await _call(test_session, "claude-opus-5", "0.35")
    await _call(test_session, "gpt-5.6-terra", "0.05")
    await _call(test_session, "gpt-5.6-terra", "9.99", cache_hit=True)  # free, not counted
    await test_session.flush()

    bot = FakeBot()
    day_start = datetime.now(UTC) - timedelta(hours=1)
    text = await _ai_cost_report_impl(test_session, bot, day_start)  # type: ignore[arg-type]

    assert "Jami: <b>$0.80</b>" in text
    assert "Anthropic · claude-opus-5" in text
    assert "$0.75 — 2 so'rov" in text
    assert "OpenAI · gpt-5.6-terra" in text
    assert "$0.05 — 1 so'rov" in text
    assert len(bot.sent) == len(settings.admin_tg_ids)


async def test_yesterdays_calls_are_not_in_todays_bill(test_session: AsyncSession) -> None:
    await _call(test_session, "claude-opus-5", "1.00")
    await test_session.flush()

    tomorrow = datetime.now(UTC) + timedelta(hours=1)
    text = await _ai_cost_report_impl(test_session, FakeBot(), tomorrow)  # type: ignore[arg-type]
    assert "Jami: <b>$0.00</b>" in text
