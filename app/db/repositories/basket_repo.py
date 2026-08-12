from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import Basket, BasketLine, Quote
from app.db.repositories.base import BaseRepository


class BasketRepository(BaseRepository[Basket]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Basket, session)

    async def create_basket(self, user_id: int, raw_text: str) -> Basket:
        basket = Basket(user_id=user_id, raw_text=raw_text, status="parsing")
        self.session.add(basket)
        await self.session.flush()
        return basket

    async def add_lines(
        self,
        basket_id: int,
        lines_data: list[dict[str, Any]],
    ) -> Sequence[BasketLine]:
        lines: list[BasketLine] = []
        for item in lines_data:
            line = BasketLine(
                basket_id=basket_id,
                line_no=item["line_no"],
                raw_text=item["raw_text"],
                parsed_name=item["parsed_name"],
                qty=item["qty"],
                unit_code=item.get("unit_code"),
                canonical_id=item.get("canonical_id"),
                match_confidence=item.get("match_confidence"),
                match_method=item.get("match_method"),
                needs_review=item.get("needs_review", False),
                user_note=item.get("user_note"),
            )
            self.session.add(line)
            lines.append(line)
        await self.session.flush()
        return lines

    async def create_quote(
        self,
        basket_id: int,
        strategy: str,
        items_total: Decimal,
        delivery_total: Decimal,
        grand_total: Decimal,
        coverage_pct: Decimal,
        shop_count: int,
        payload: dict[str, Any],
        eta_hours: int | None = None,
        missing_line_ids: list[int] | None = None,
    ) -> Quote:
        quote = Quote(
            basket_id=basket_id,
            strategy=strategy,
            items_total=items_total,
            delivery_total=delivery_total,
            grand_total=grand_total,
            coverage_pct=coverage_pct,
            shop_count=shop_count,
            eta_hours=eta_hours,
            missing_line_ids=missing_line_ids or [],
            payload=payload,
        )
        self.session.add(quote)
        await self.session.flush()
        return quote

    async def get_quote(self, quote_id: int) -> Quote | None:
        return await self.session.get(Quote, quote_id)
