"""Pebble balance is the sum of its ledger, and an order grants exactly once."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.repositories import OpsRepository


async def _user(session: AsyncSession, tg_id: int = 1234) -> User:
    user = User(tg_id=tg_id, full_name="Mijoz", lang="uz_latn", role="customer")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_balance_starts_at_zero_and_sums_awards(test_session: AsyncSession) -> None:
    user = await _user(test_session)
    repo = OpsRepository(test_session)

    assert await repo.get_pebble_balance(user.id) == 0

    await repo.award_pebbles(user_id=user.id, amount=638, source="order", order_id=1)
    await repo.award_pebbles(user_id=user.id, amount=100, source="bonus")
    assert await repo.get_pebble_balance(user.id) == 738


@pytest.mark.asyncio
async def test_the_same_order_cannot_grant_twice(test_session: AsyncSession) -> None:
    """Confirmation can be retried; that must not mint currency again."""
    user = await _user(test_session)
    repo = OpsRepository(test_session)

    await repo.award_pebbles(user_id=user.id, amount=500, source="order", order_id=7)
    await repo.award_pebbles(user_id=user.id, amount=500, source="order", order_id=7)

    assert await repo.get_pebble_balance(user.id) == 500


@pytest.mark.asyncio
async def test_non_positive_awards_are_not_recorded(test_session: AsyncSession) -> None:
    user = await _user(test_session)
    repo = OpsRepository(test_session)

    assert await repo.award_pebbles(user_id=user.id, amount=0, source="order", order_id=9) is None
    assert await repo.award_pebbles(user_id=user.id, amount=-5, source="bonus") is None
    assert await repo.get_pebble_balance(user.id) == 0


@pytest.mark.asyncio
async def test_balances_do_not_leak_between_users(test_session: AsyncSession) -> None:
    first = await _user(test_session, tg_id=111)
    second = await _user(test_session, tg_id=222)
    repo = OpsRepository(test_session)

    await repo.award_pebbles(user_id=first.id, amount=300, source="order", order_id=1)
    assert await repo.get_pebble_balance(first.id) == 300
    assert await repo.get_pebble_balance(second.id) == 0


@pytest.mark.asyncio
async def test_order_total_maps_to_the_configured_rate(test_session: AsyncSession) -> None:
    """End to end: the rate in config is what a real order total earns."""
    from app.core.config import settings
    from app.domain.rewards import pebbles_for_order

    user = await _user(test_session)
    repo = OpsRepository(test_session)

    earned = pebbles_for_order(Decimal("638200"), settings.pebble_rate_per_order)
    await repo.award_pebbles(user_id=user.id, amount=earned, source="order", order_id=42)

    assert earned == 638
    assert await repo.get_pebble_balance(user.id) == 638
