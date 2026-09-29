"""The admin dashboard shows only recent real orders for the house shop."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.shop import Shop
from app.web.storefront.pricing import format_money
from tests.integration.test_storefront_web import _seed, _sign_in, _sign_in_admin
from tests.integration.test_storefront_web import client as storefront_client


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_dashboard_recent_orders_scope_limit_fallbacks_and_links(
    client: TestClient, test_session: AsyncSession
) -> None:
    fixture = await _seed(test_session)
    house_shop = await test_session.get(Shop, fixture.shop_id)
    assert house_shop is not None

    other_shop = Shop(
        name="Other shop",
        phone="+998901234567",
        district_id=house_shop.district_id,
        address="Other address",
    )
    basket = Basket(user_id=fixture.user_id, raw_text="dashboard order fixture")
    test_session.add_all([other_shop, basket])
    await test_session.flush()

    base_time = datetime.now(UTC) - timedelta(hours=2)

    async def add_order(
        *,
        index: int,
        shop_id: int,
        is_test: bool = False,
        contact_name: str | None = "Test Customer",
    ) -> int:
        amount = Decimal(1000 + index)
        quote = Quote(
            basket_id=basket.id,
            strategy="cheapest",
            items_total=amount,
            delivery_total=Decimal("0"),
            grand_total=amount,
            coverage_pct=Decimal("100"),
            shop_count=1,
            payload={},
        )
        test_session.add(quote)
        await test_session.flush()
        order = Order(
            quote_id=quote.id,
            user_id=fixture.user_id,
            status="new",
            contact_phone="+998901234567",
            contact_name=contact_name,
            delivery_address="Test address",
            grand_total_quoted=amount,
            is_test=is_test,
            created_at=base_time + timedelta(minutes=index),
        )
        test_session.add(order)
        await test_session.flush()
        test_session.add(
            OrderShopPart(
                order_id=order.id,
                shop_id=shop_id,
                subtotal=amount,
                delivery_fee=Decimal("0"),
                status="new",
                shop_response="pending",
            )
        )
        await test_session.flush()
        return order.id

    house_order_ids = [
        await add_order(
            index=index,
            shop_id=fixture.shop_id,
            contact_name=None if index == 6 else f"Customer {index}",
        )
        for index in range(7)
    ]
    other_order_id = await add_order(
        index=20, shop_id=other_shop.id, contact_name="Other shop customer"
    )
    test_order_id = await add_order(
        index=21, shop_id=fixture.shop_id, is_test=True, contact_name="Test order"
    )
    await test_session.flush()

    # A regular customer cannot see the admin dashboard.
    _sign_in(client, fixture.user_id)
    assert client.get("/manage").status_code == 403

    await _sign_in_admin(client, test_session)
    response = client.get("/manage")
    assert response.status_code == 200
    expected_ids = list(reversed(house_order_ids[-5:]))
    for order_id in expected_ids:
        assert f'href="/shop/{fixture.shop_id}/orders#order-{order_id}"' in response.text
        assert f"#{order_id}" in response.text
    for order_id in house_order_ids[:2] + [other_order_id, test_order_id]:
        assert f"#{order_id}" not in response.text
        assert f'href="/shop/{fixture.shop_id}/orders#order-{order_id}"' not in response.text

    assert response.text.count('class="admin-order-state order-new"') == 5
    assert "Yangi" in response.text
    assert "Customer 6" not in response.text
    assert "—" in response.text
    expected_amount = format_money(Decimal("1006.00"), "UZS", "uz_latn")
    assert expected_amount.replace("'", "&#39;") in response.text
