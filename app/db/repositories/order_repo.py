from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import Order, OrderItem, OrderShopPart
from app.db.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Order, session)

    async def create_order(
        self,
        quote_id: int,
        user_id: int,
        contact_phone: str,
        delivery_address: str,
        grand_total_quoted: Decimal,
        comment: str | None = None,
        shop_parts_data: list[dict[str, Any]] | None = None,
    ) -> Order:
        order = Order(
            quote_id=quote_id,
            user_id=user_id,
            contact_phone=contact_phone,
            delivery_address=delivery_address,
            grand_total_quoted=grand_total_quoted,
            comment=comment,
            status="new",
        )
        self.session.add(order)
        await self.session.flush()

        if shop_parts_data:
            for part_data in shop_parts_data:
                part = OrderShopPart(
                    order_id=order.id,
                    shop_id=part_data["shop_id"],
                    subtotal=part_data["subtotal"],
                    delivery_fee=part_data.get("delivery_fee", Decimal("0.00")),
                    status="new",
                    shop_response="pending",
                )
                self.session.add(part)
                await self.session.flush()

                for item_data in part_data.get("items", []):
                    item = OrderItem(
                        order_shop_part_id=part.id,
                        canonical_id=item_data["canonical_id"],
                        shop_product_id=item_data["shop_product_id"],
                        qty=item_data["qty"],
                        unit_code=item_data["unit_code"],
                        unit_price_quoted=item_data["unit_price_quoted"],
                        line_total=item_data["line_total"],
                    )
                    self.session.add(item)

        await self.session.flush()
        return order

    async def get_customer_orders(self, user_id: int, limit: int = 10) -> list[Order]:
        from sqlalchemy import select

        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_shop_response(
        self,
        order_shop_part_id: int,
        response: str,  # accepted|rejected|partial
    ) -> OrderShopPart | None:
        part = await self.session.get(OrderShopPart, order_shop_part_id)
        if not part:
            return None
        part.shop_response = response
        part.responded_at = datetime.now(UTC)
        await self.session.flush()
        return part
