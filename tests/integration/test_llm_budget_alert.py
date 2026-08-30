"""The AI budget must announce itself before it runs out.

Running out is silent by construction: every LLM stage simply stops answering,
baskets get quietly worse, and the cause is a number in an environment
variable. These tests pin the two things that make the warning useful -- it
arrives early, and it arrives once.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.ops import Event
from app.db.repositories.ops_repo import OpsRepository
from app.services.llm_budget_alert import BUDGET_WARNING_EVENT, warn_admins_if_budget_low


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    """No admin ids means notify_admins has nobody to call, so nothing leaves the box."""
    monkeypatch.setattr(settings, "admin_tg_ids", [])


async def _warnings_logged(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count(Event.id)).where(Event.name == BUDGET_WARNING_EVENT)
    )
    return int(result.scalar() or 0)


@pytest.mark.asyncio
async def test_quiet_while_there_is_room(test_session: AsyncSession) -> None:
    used = int(settings.llm_daily_token_budget * 0.5)
    assert await warn_admins_if_budget_low(test_session, used) is False
    assert await _warnings_logged(test_session) == 0


@pytest.mark.asyncio
async def test_warns_at_the_last_tenth(test_session: AsyncSession) -> None:
    used = int(settings.llm_daily_token_budget * settings.llm_budget_warn_ratio) + 1
    assert await warn_admins_if_budget_low(test_session, used) is True
    assert await _warnings_logged(test_session) == 1


@pytest.mark.asyncio
async def test_says_it_once_a_day(test_session: AsyncSession) -> None:
    """The check runs on the path of every LLM call; the admins get one message."""
    used = settings.llm_daily_token_budget
    assert await warn_admins_if_budget_low(test_session, used) is True
    assert await warn_admins_if_budget_low(test_session, used + 5000) is False
    assert await _warnings_logged(test_session) == 1


@pytest.mark.asyncio
async def test_the_warning_reaches_the_llm_path(test_session: AsyncSession) -> None:
    """Spending the budget through the client is what triggers it in production."""
    from app.llm.client import LLMClient

    ops_repo = OpsRepository(test_session)
    await ops_repo.record_llm_call(
        purpose="batch_disambiguation",
        prompt_version="v1",
        input_hash="nearly-spent",
        input_tokens=int(settings.llm_daily_token_budget * 0.95),
        output_tokens=0,
        cost_usd=Decimal("0.10"),
        latency_ms=10,
        cache_hit=False,
        raw_response="{}",
    )
    await test_session.flush()

    client = LLMClient(session=test_session, mock_mode=True)
    # Still inside the budget, so the call is allowed -- and the admins are told.
    assert await client._has_token_budget() is True
    assert await _warnings_logged(test_session) == 1
