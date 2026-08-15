from collections.abc import Sequence
from datetime import date as date_
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import DailyMetrics, Event, LLMCall, PebbleAward, UnmatchedQuery
from app.db.models.order import Basket, BasketLine, Order, Quote
from app.db.models.shop import ShopProduct
from app.db.repositories.base import BaseRepository


class OpsRepository(BaseRepository[UnmatchedQuery]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(UnmatchedQuery, session)

    async def record_unmatched_query(
        self,
        raw_text: str,
        normalized: str,
        user_id: int | None = None,
        suggested_canonical_id: int | None = None,
    ) -> UnmatchedQuery:
        stmt = select(UnmatchedQuery).where(UnmatchedQuery.normalized == normalized)
        result = await self.session.execute(stmt)
        record = result.scalars().first()

        if record:
            record.occurrences += 1
            if suggested_canonical_id and not record.suggested_canonical_id:
                record.suggested_canonical_id = suggested_canonical_id
            await self.session.flush()
            return record

        record = UnmatchedQuery(
            raw_text=raw_text,
            normalized=normalized,
            user_id=user_id,
            occurrences=1,
            suggested_canonical_id=suggested_canonical_id,
            status="new",
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def record_llm_call(
        self,
        purpose: str,
        prompt_version: str,
        input_hash: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
        latency_ms: int,
        cache_hit: bool = False,
        raw_response: str | None = None,
    ) -> LLMCall:
        call = LLMCall(
            purpose=purpose,
            prompt_version=prompt_version,
            input_hash=input_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            raw_response=raw_response,
        )
        self.session.add(call)
        await self.session.flush()
        return call

    async def log_event(
        self,
        name: str,
        user_id: int | None = None,
        props: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            name=name,
            user_id=user_id,
            props=props or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

    # ─── Background Job / Admin Digest Queries (§10, §11, §12) ─────

    async def get_top_unmatched(self, limit: int = 10) -> Sequence[UnmatchedQuery]:
        stmt = (
            select(UnmatchedQuery)
            .where(UnmatchedQuery.status == "new")
            .order_by(UnmatchedQuery.occurrences.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_stale_shops(self) -> int:
        """Distinct shops with at least one active offer that has gone stale."""
        stmt = select(func.count(func.distinct(ShopProduct.shop_id))).where(
            ShopProduct.is_active.is_(True),
            ShopProduct.staleness_state == "stale",
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def get_order_stats(self, start: datetime, end: datetime) -> tuple[int, Decimal]:
        stmt = select(
            func.count(),
            func.coalesce(
                func.sum(func.coalesce(Order.grand_total_final, Order.grand_total_quoted)), 0
            ),
        ).where(Order.created_at >= start, Order.created_at < end, Order.status != "cancelled")
        result = await self.session.execute(stmt)
        count, gmv = result.one()
        return int(count), Decimal(str(gmv))

    async def get_llm_cost_total(self, start: datetime, end: datetime) -> Decimal:
        stmt = select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(
            LLMCall.created_at >= start, LLMCall.created_at < end
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar() or 0))

    async def get_basket_line_stats(
        self, start: datetime, end: datetime
    ) -> tuple[int, int, int, int]:
        """Returns (basket_count, total_lines, matched_lines, auto_matched_lines)."""
        basket_count_stmt = select(func.count()).where(
            Basket.created_at >= start, Basket.created_at < end
        )
        basket_count = int((await self.session.execute(basket_count_stmt)).scalar() or 0)

        line_stmt = (
            select(
                func.count(),
                func.sum(case((BasketLine.canonical_id.is_not(None), 1), else_=0)),
                func.sum(
                    case(
                        (
                            BasketLine.match_method.in_(["alias", "trgm"])
                            & BasketLine.needs_review.is_(False),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
            .join(Basket, Basket.id == BasketLine.basket_id)
            .where(Basket.created_at >= start, Basket.created_at < end)
        )
        result = await self.session.execute(line_stmt)
        total_lines, matched_lines, auto_matched_lines = result.one()
        return (
            basket_count,
            int(total_lines or 0),
            int(matched_lines or 0),
            int(auto_matched_lines or 0),
        )

    async def get_quote_and_strategy_stats(
        self, start: datetime, end: datetime
    ) -> tuple[int, dict[str, int]]:
        """Returns (quote_count, {strategy: count})."""
        stmt = (
            select(Quote.strategy, func.count())
            .where(Quote.created_at >= start, Quote.created_at < end)
            .group_by(Quote.strategy)
        )
        result = await self.session.execute(stmt)
        mix = {strategy: int(count) for strategy, count in result.all()}
        return sum(mix.values()), mix

    async def get_price_freshness_pct(self) -> Decimal:
        stmt = select(
            func.sum(case((ShopProduct.staleness_state == "fresh", 1), else_=0)),
            func.count(),
        ).where(ShopProduct.is_active.is_(True))
        result = await self.session.execute(stmt)
        fresh, total = result.one()
        if not total:
            return Decimal("0.00")
        return (Decimal(fresh) / Decimal(total) * 100).quantize(Decimal("0.01"))

    async def write_daily_metrics(self, day: date_, **fields: Any) -> DailyMetrics:
        """Idempotent upsert by date, so rollup_metrics is safe to re-run."""
        stmt = select(DailyMetrics).where(DailyMetrics.date == day)
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing

        record = DailyMetrics(date=day, **fields)
        self.session.add(record)
        await self.session.flush()
        return record

    async def mark_unmatched_resolved(self, query_id: int, resolved_alias_id: int) -> None:
        stmt = (
            update(UnmatchedQuery)
            .where(UnmatchedQuery.id == query_id)
            .values(status="resolved", resolved_alias_id=resolved_alias_id)
        )
        await self.session.execute(stmt)

    async def mark_unmatched_junk(self, query_id: int) -> None:
        stmt = update(UnmatchedQuery).where(UnmatchedQuery.id == query_id).values(status="junk")
        await self.session.execute(stmt)

    async def list_recent_daily_metrics(self, limit: int = 30) -> Sequence[DailyMetrics]:
        stmt = select(DailyMetrics).order_by(DailyMetrics.date.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_llm_cost_by_purpose(self, since: datetime) -> dict[str, Decimal]:
        stmt = (
            select(LLMCall.purpose, func.coalesce(func.sum(LLMCall.cost_usd), 0))
            .where(LLMCall.created_at >= since)
            .group_by(LLMCall.purpose)
        )
        result = await self.session.execute(stmt)
        return {purpose: Decimal(str(cost)) for purpose, cost in result.all()}

    # ─── Pebble rewards ────────────────────────────────────────────

    async def award_pebbles(
        self,
        user_id: int,
        amount: int,
        source: str,
        order_id: int | None = None,
        note: str | None = None,
    ) -> PebbleAward | None:
        """Record a pebble grant, ignoring a repeat award for the same order.

        Confirmation can be retried (a double tap, a redelivered update), and
        the unique (order_id, source) constraint is what stops that minting
        currency twice -- this checks first so the caller does not have to
        handle the integrity error.
        """
        if amount <= 0:
            return None
        if order_id is not None:
            stmt = select(PebbleAward).where(
                PebbleAward.order_id == order_id, PebbleAward.source == source
            )
            existing = (await self.session.execute(stmt)).scalars().first()
            if existing is not None:
                return existing

        award = PebbleAward(
            user_id=user_id, amount=amount, source=source, order_id=order_id, note=note
        )
        self.session.add(award)
        await self.session.flush()
        return award

    async def get_pebble_balance(self, user_id: int) -> int:
        stmt = select(func.coalesce(func.sum(PebbleAward.amount), 0)).where(
            PebbleAward.user_id == user_id
        )
        return int(await self.session.scalar(stmt) or 0)
