"""Scheduled job implementations (SPEC §10).

Each public job function (the arq entrypoints) acquires its advisory lock, opens a
session, delegates to a testable `_*_impl` that does the actual work against an
injected `AsyncSession`/`Bot`, then commits. Tests call the `_*_impl` functions
directly against the `test_session` fixture — no separate engine/connection involved.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import get_price_nudge_keyboard
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.ops import DailyMetrics
from app.db.repositories.basket_repo import BasketRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import async_session_factory
from app.workers.locks import try_acquire_job_lock

logger = get_logger(__name__)


async def _mark_price_staleness_impl(session: AsyncSession) -> tuple[int, int]:
    now = datetime.now(UTC)
    aging_cutoff = now - timedelta(days=settings.price_staleness_aging_days)
    stale_cutoff = now - timedelta(days=settings.price_staleness_stale_days)

    shop_repo = ShopRepository(session)
    candidates = await shop_repo.list_active_offers_updated_before(aging_cutoff)

    aging_ids = [
        o.id for o in candidates if o.updated_at >= stale_cutoff and o.staleness_state != "aging"
    ]
    stale_ids = [
        o.id for o in candidates if o.updated_at < stale_cutoff and o.staleness_state != "stale"
    ]

    await shop_repo.bulk_set_staleness(aging_ids, "aging")
    await shop_repo.bulk_set_staleness(stale_ids, "stale")
    return len(aging_ids), len(stale_ids)


async def mark_price_staleness(ctx: dict[str, Any]) -> None:
    """Hourly: escalate offer staleness_state by age (§10)."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "mark_price_staleness"):
            logger.info("job_skipped_locked", job="mark_price_staleness")
            return
        aging, stale = await _mark_price_staleness_impl(session)
        await session.commit()
        logger.info("mark_price_staleness_done", aging=aging, stale=stale)


async def _nudge_shops_impl(session: AsyncSession, bot: Bot) -> tuple[int, int]:
    shop_repo = ShopRepository(session)
    shops = await shop_repo.list_shops_with_aging_offers()

    keyboard = get_price_nudge_keyboard()
    sent = 0
    for shop in shops:
        if not shop.owner_tg_id:
            continue
        try:
            await bot.send_message(
                shop.owner_tg_id,
                f"⚠️ «{shop.name}» do'koningizdagi ba'zi narxlar eskirmoqda. "
                "Iltimos, narxlarni yangilang.",
                reply_markup=keyboard,
            )
            sent += 1
        except TelegramAPIError as exc:
            logger.warning("nudge_send_failed", shop_id=shop.id, error=str(exc))
    return len(shops), sent


async def nudge_shops(ctx: dict[str, Any]) -> None:
    """Daily 09:00: DM owners of shops with aging offers (§10)."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "nudge_shops"):
            logger.info("job_skipped_locked", job="nudge_shops")
            return
        shops, sent = await _nudge_shops_impl(session, ctx["bot"])
        await session.commit()
        logger.info("nudge_shops_done", shops=shops, sent=sent)


async def _recompute_trust_scores_impl(session: AsyncSession) -> int:
    """freshness*0.5 + accept_rate*0.3 + rating*0.2 (§10).

    `rating` is on a 0-5 scale while `trust_score` is 0-1, so rating is normalized
    (rating/5) before weighting. Shops with no offers/order history yet default to
    1.0 on that signal rather than 0, so a brand-new shop isn't punished for having
    no track record.
    """
    shop_repo = ShopRepository(session)
    since = datetime.now(UTC) - timedelta(days=settings.trust_score_window_days)

    freshness_by_shop = await shop_repo.compute_freshness_ratios()
    accept_rate_by_shop = await shop_repo.compute_accept_rates(since)
    shops = await shop_repo.list_active_shops()

    updated = 0
    for shop in shops:
        freshness = freshness_by_shop.get(shop.id, Decimal("1"))
        accept_rate = accept_rate_by_shop.get(shop.id, Decimal("1"))
        rating_normalized = Decimal(shop.rating) / Decimal("5")

        trust_score = (
            freshness * Decimal(str(settings.trust_score_freshness_weight))
            + accept_rate * Decimal(str(settings.trust_score_accept_rate_weight))
            + rating_normalized * Decimal(str(settings.trust_score_rating_weight))
        ).quantize(Decimal("0.01"))
        trust_score = min(Decimal("1.00"), max(Decimal("0.00"), trust_score))

        await shop_repo.update_trust_score(shop.id, trust_score)
        updated += 1
    return updated


async def recompute_trust_scores(ctx: dict[str, Any]) -> None:
    """Daily 03:00 (§10)."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "recompute_trust_scores"):
            logger.info("job_skipped_locked", job="recompute_trust_scores")
            return
        updated = await _recompute_trust_scores_impl(session)
        await session.commit()
        logger.info("recompute_trust_scores_done", shops=updated)


async def _rollup_metrics_impl(session: AsyncSession, day_start: datetime) -> DailyMetrics:
    day_end = day_start + timedelta(days=1)

    ops_repo = OpsRepository(session)
    (
        basket_count,
        total_lines,
        matched_lines,
        auto_matched_lines,
    ) = await ops_repo.get_basket_line_stats(day_start, day_end)
    quote_count, strategy_mix = await ops_repo.get_quote_and_strategy_stats(day_start, day_end)
    order_count, gmv = await ops_repo.get_order_stats(day_start, day_end)
    llm_cost_usd = await ops_repo.get_llm_cost_total(day_start, day_end)
    price_freshness_pct = await ops_repo.get_price_freshness_pct()

    match_rate = (
        (Decimal(matched_lines) / Decimal(total_lines) * 100) if total_lines else Decimal("0")
    )
    auto_match_rate = (
        (Decimal(auto_matched_lines) / Decimal(total_lines) * 100) if total_lines else Decimal("0")
    )
    avg_lines_per_basket = (
        (Decimal(total_lines) / Decimal(basket_count)) if basket_count else Decimal("0")
    )
    quote_to_order_rate = (
        (Decimal(order_count) / Decimal(quote_count) * 100) if quote_count else Decimal("0")
    )

    return await ops_repo.write_daily_metrics(
        day_start.date(),
        gmv=gmv,
        order_count=order_count,
        basket_count=basket_count,
        match_rate=match_rate.quantize(Decimal("0.01")),
        auto_match_rate=auto_match_rate.quantize(Decimal("0.01")),
        avg_lines_per_basket=avg_lines_per_basket.quantize(Decimal("0.01")),
        quote_to_order_rate=quote_to_order_rate.quantize(Decimal("0.01")),
        price_freshness_pct=price_freshness_pct,
        llm_cost_usd=llm_cost_usd,
        strategy_mix=strategy_mix,
    )


async def rollup_metrics(ctx: dict[str, Any]) -> None:
    """Daily 04:00: write yesterday's funnel into daily_metrics (§10)."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "rollup_metrics"):
            logger.info("job_skipped_locked", job="rollup_metrics")
            return
        now = datetime.now(UTC)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
        record = await _rollup_metrics_impl(session, day_start)
        await session.commit()
        logger.info("rollup_metrics_done", date=str(record.date))


async def _admin_digest_impl(session: AsyncSession, bot: Bot, day_start: datetime) -> str:
    day_end = day_start + timedelta(days=1)
    ops_repo = OpsRepository(session)
    top_unmatched = await ops_repo.get_top_unmatched(limit=5)
    stale_shop_count = await ops_repo.count_stale_shops()
    order_count, gmv = await ops_repo.get_order_stats(day_start, day_end)

    lines = ["📋 <b>Kunlik hisobot</b>\n"]
    lines.append(f"• Kecha buyurtmalar: <b>{order_count}</b>, GMV: <b>{gmv:,.0f} so'm</b>")
    lines.append(f"• Eskirgan narxli do'konlar: <b>{stale_shop_count}</b>")
    if top_unmatched:
        lines.append("\n<b>Eng ko'p topilmagan so'rovlar:</b>")
        for q in top_unmatched:
            lines.append(f"• «{q.raw_text}» — {q.occurrences}x")
    digest_text = "\n".join(lines)

    for admin_id in settings.admin_tg_ids:
        try:
            await bot.send_message(admin_id, digest_text)
        except TelegramAPIError as exc:
            logger.warning("admin_digest_send_failed", admin_id=admin_id, error=str(exc))
    return digest_text


async def admin_digest(ctx: dict[str, Any]) -> None:
    """Daily 08:00: DM admins top unmatched queries, stale shops, orders, GMV (§10)."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "admin_digest"):
            logger.info("job_skipped_locked", job="admin_digest")
            return
        now = datetime.now(UTC)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC) - timedelta(days=1)
        await _admin_digest_impl(session, ctx["bot"], day_start)
        await session.commit()
        logger.info("admin_digest_done", admins=len(settings.admin_tg_ids))


async def _abandon_baskets_impl(session: AsyncSession, cutoff: datetime) -> int:
    basket_repo = BasketRepository(session)
    stale_baskets = await basket_repo.list_stale_awaiting_confirmation(cutoff)
    await basket_repo.bulk_mark_abandoned([b.id for b in stale_baskets])
    return len(stale_baskets)


async def abandon_baskets(ctx: dict[str, Any]) -> None:
    """Every 30 min: baskets stuck in awaiting_confirmation > 24h -> abandoned (§10)."""
    async with async_session_factory() as session:
        if not await try_acquire_job_lock(session, "abandon_baskets"):
            logger.info("job_skipped_locked", job="abandon_baskets")
            return
        cutoff = datetime.now(UTC) - timedelta(hours=settings.basket_abandon_hours)
        count = await _abandon_baskets_impl(session, cutoff)
        await session.commit()
        logger.info("abandon_baskets_done", count=count)
