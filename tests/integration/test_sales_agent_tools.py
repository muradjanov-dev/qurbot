"""The agent's tools against a real (SQLite) catalogue: search, basket, quote, order checks."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category
from app.db.models.shop import District, Shop, ShopProduct
from app.db.models.user import User
from app.services.sales_agent import AgentCart, DbAgentTools


@pytest.fixture(autouse=True)
def _full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enabled_category_slugs", [])


async def _seed(session: AsyncSession) -> tuple[User, int]:
    category = Category(slug="plita-va-fanera", name_uz="Plita va fanera", name_ru="Плита")
    session.add(category)
    await session.flush()
    product = CanonicalProduct(
        slug="fanera-10mm-1525x1525",
        name_uz="Fanera 10 mm 1525x1525",
        name_uz_cyrl="Фанера 10 мм 1525х1525",
        name_ru="Фанера 10 мм 1525х1525",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="fanera 10 mm 1525x1525 фанера 10 мм",
        attributes={"thickness_mm": 10, "size": "1525x1525"},
    )
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add_all([product, district])
    await session.flush()
    shop = Shop(
        name="Test shop",
        phone="+998901112233",
        district_id=district.id,
        address="Chilonzor 9-kvartal",
        is_active=True,
    )
    user = User(tg_id=555, lang="uz_latn", district_id=district.id)
    session.add_all([shop, user])
    await session.flush()
    session.add(
        ShopProduct(
            shop_id=shop.id,
            canonical_id=product.id,
            raw_name="Fanera 10 mm 1525x1525",
            raw_unit="dona",
            pack_size=Decimal("1"),
            pack_unit_code="dona",
            price_per_pack=Decimal("151000"),
            price_per_base_unit=Decimal("151000"),
            stock_status="in_stock",
            staleness_state="fresh",
            is_active=True,
        )
    )
    await session.flush()
    return user, product.id


async def test_search_returns_stocked_products_with_price(test_session: AsyncSession) -> None:
    user, product_id = await _seed(test_session)
    result = await DbAgentTools(test_session, user).run(
        "search_products", {"query": "fanera 10mm"}, AgentCart()
    )
    assert result["products"][0]["id"] == product_id
    assert result["products"][0]["price_from_uzs"] == "151000"


async def test_basket_quote_and_order_details(test_session: AsyncSession) -> None:
    user, product_id = await _seed(test_session)
    tools = DbAgentTools(test_session, user)
    cart = AgentCart()

    # Ordering before a quote is refused.
    early = await tools.run("prepare_order", {"phone": "901234567", "address": "x"}, cart)
    assert "error" in early

    await tools.run("set_basket_item", {"product_id": product_id, "qty": 3}, cart)
    assert cart.basket[0]["qty"] == "3"

    quote = await tools.run("get_quote", {}, cart)
    assert quote["orderable"] is True
    assert cart.quote is not None

    bad_phone = await tools.run(
        "prepare_order", {"phone": "123", "address": "Chilonzor 9-kvartal 12-uy"}, cart
    )
    assert "error" in bad_phone
    ok = await tools.run(
        "prepare_order", {"phone": "+998901234567", "address": "Chilonzor 9-kvartal 12-uy"}, cart
    )
    assert ok["ok"] is True
    assert cart.order is not None and cart.order["phone"] == "+998901234567"

    # Changing the basket makes the quote and order stale.
    await tools.run("set_basket_item", {"product_id": product_id, "qty": 0}, cart)
    assert cart.basket == [] and cart.quote is None and cart.order is None


async def test_invented_products_are_refused(test_session: AsyncSession) -> None:
    user, _ = await _seed(test_session)
    result = await DbAgentTools(test_session, user).run(
        "set_basket_item", {"product_id": 99999, "qty": 1}, AgentCart()
    )
    assert result == {"error": "product not found"}


async def test_catalogue_only_product_has_no_invented_price(test_session: AsyncSession) -> None:
    from sqlalchemy import delete

    user, product_id = await _seed(test_session)
    await test_session.execute(delete(ShopProduct))
    product = await test_session.get(CanonicalProduct, product_id)
    assert product is not None
    product.attributes = {**product.attributes, "price_on_request": True, "stock_unverified": True}
    await test_session.flush()
    result = await DbAgentTools(test_session, user).run(
        "search_products", {"query": "fanera"}, AgentCart()
    )
    card = next(card for card in result["products"] if card["id"] == product_id)
    assert card["price_from_uzs"] is None
    assert card["price_on_request"] and card["stock_unverified"]
    assert card["reference"] == f"/product/{product_id}"
    assert card["unit_code"] == "dona"
    tools = DbAgentTools(test_session, user)
    assert await tools.run(
        "set_basket_item", {"product_id": product_id, "qty": 1}, AgentCart()
    ) == {"error": "operator_confirmation_required"}
    cart = AgentCart(
        basket=[{"canonical_id": product_id, "name": "Fanera", "qty": "1", "unit_code": "dona"}]
    )
    assert await tools.run("get_quote", {}, cart) == {"error": "operator_confirmation_required"}


async def test_knowledge_returns_actual_support_and_delivery(
    test_session: AsyncSession, monkeypatch
) -> None:
    from sqlalchemy import select

    from app.db.models.shop import ShopDeliveryRule

    user, _ = await _seed(test_session)
    shop = await test_session.scalar(select(Shop))
    monkeypatch.setattr(settings, "house_shop_name", shop.name)
    monkeypatch.setattr(settings, "support_phones", ["+998901234567"])
    test_session.add(
        ShopDeliveryRule(
            shop_id=shop.id,
            district_id=None,
            fee=Decimal("12345"),
            min_order=Decimal("20000"),
            eta_hours=48,
            is_pickup_only=False,
        )
    )
    await test_session.flush()
    result = await DbAgentTools(test_session, user).run("get_knowledge", {}, AgentCart())
    assert result["support_phones"] == ["+998901234567"]
    assert Decimal(result["delivery_rules"][0]["fee_uzs"]) == Decimal("12345")
