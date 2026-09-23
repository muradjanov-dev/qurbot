"""The agent's tools against a real (SQLite) catalogue: search, basket, quote, order checks."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category
from app.db.models.order import Order
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
    added = await tools.run("set_basket_item", {"product_id": product_id, "qty": 1}, AgentCart())
    assert added["basket"][0]["canonical_id"] == product_id
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


async def test_agent_picks_a_district_before_quoting(test_session: AsyncSession) -> None:
    """The agent has to be able to ask where the order is going, and be told.

    Delivery is priced per district. Before this the agent could only ever use
    users.district_id, so a guest -- or anyone ordering to a site that is not
    their saved district -- had no way to reach a total at all.
    """
    user, product_id = await _seed(test_session)
    user.district_id = None
    await test_session.flush()
    tools = DbAgentTools(test_session, user)
    cart = AgentCart()
    await tools.run("set_basket_item", {"product_id": product_id, "qty": 2}, cart)

    regions = await tools.run("get_delivery_options", {}, cart)
    assert "Toshkent" in regions["regions"]
    assert regions["current"] is None

    listed = await tools.run("get_delivery_options", {"region": "Toshkent"}, cart)
    chosen = listed["districts"][0]

    # An id the agent did not get from the tool is refused rather than used.
    assert "error" in await tools.run("set_delivery_district", {"district_id": 999999}, cart)
    assert "error" in await tools.run("set_delivery_district", {"district_id": "abc"}, cart)

    assert (await tools.run("set_delivery_district", {"district_id": chosen["id"]}, cart))["ok"]
    assert cart.district_id == chosen["id"]

    quote = await tools.run("get_quote", {}, cart)
    assert quote["orderable"] is True

    prepared = await tools.run(
        "prepare_order", {"phone": "+998901234567", "address": "Chilonzor 9-kvartal 12-uy"}, cart
    )
    assert prepared["ok"] is True
    assert cart.order is not None
    assert cart.order["district_id"] == str(chosen["id"])


async def test_changing_district_invalidates_the_quote(test_session: AsyncSession) -> None:
    user, product_id = await _seed(test_session)
    other = District(region="Toshkent", name_uz="Yunusobod", name_ru="Юнусабад")
    test_session.add(other)
    await test_session.flush()
    tools = DbAgentTools(test_session, user)
    cart = AgentCart()
    await tools.run("set_basket_item", {"product_id": product_id, "qty": 1}, cart)
    await tools.run("set_delivery_district", {"district_id": user.district_id}, cart)
    await tools.run("get_quote", {}, cart)
    await tools.run(
        "prepare_order", {"phone": "+998901234567", "address": "Chilonzor 9-kvartal 12-uy"}, cart
    )
    assert cart.quote is not None and cart.order is not None

    # A quote is priced for one destination; moving it makes both stale.
    await tools.run("set_delivery_district", {"district_id": other.id}, cart)
    assert cart.quote is None and cart.order is None
    assert "error" in await tools.run(
        "prepare_order", {"phone": "+998901234567", "address": "Chilonzor 9-kvartal 12-uy"}, cart
    )


async def test_prepare_order_refuses_without_a_district(test_session: AsyncSession) -> None:
    user, product_id = await _seed(test_session)
    user.district_id = None
    await test_session.flush()
    tools = DbAgentTools(test_session, user)
    cart = AgentCart()
    await tools.run("set_basket_item", {"product_id": product_id, "qty": 1}, cart)
    await tools.run("get_quote", {}, cart)
    cart.quote = cart.quote or None
    result = await tools.run(
        "prepare_order", {"phone": "+998901234567", "address": "Chilonzor 9-kvartal 12-uy"}, cart
    )
    assert "error" in result


async def test_agent_submits_an_unpriced_basket_as_an_enquiry(
    test_session: AsyncSession,
) -> None:
    """An unknown price must not dead-end the chat.

    Before this the agent could only tell the customer which buttons to press
    and the conversation stopped there. It now takes the four details and files
    the enquiry itself -- which is emphatically not an order: nothing is sold,
    and the conversation goes to an operator.
    """
    from app.db.models.sales_request import SalesRequest
    from app.services.cart_service import CartService

    user, product_id = await _seed(test_session)
    unpriced = CanonicalProduct(
        slug="fanera-18mm-on-request",
        name_uz="Fanera 18 mm",
        name_uz_cyrl="Фанера 18 мм",
        name_ru="Фанера 18 мм",
        category_id=(await test_session.get(CanonicalProduct, product_id)).category_id,
        base_unit_code="dona",
        search_doc="fanera 18 mm",
        attributes={"price_on_request": True, "stock_unverified": True},
    )
    test_session.add(unpriced)
    await test_session.flush()

    tools = DbAgentTools(test_session, user)
    cart = AgentCart()
    await tools.run("set_basket_item", {"product_id": unpriced.id, "qty": 4}, cart)

    # DbAgentTools only moves the agent's own view of the basket; the shared
    # cart row is written by DurableTools in the worker. Stand in for it here,
    # because the enquiry is built from the stored cart, not from the model's
    # recollection of it.
    shared = CartService(test_session)
    snapshot = await shared.set_item(
        user.id, unpriced.id, "4", expected_revision=(await shared.get(user.id)).revision
    )
    cart.revision = snapshot.revision

    # A basket that cannot be priced is refused a total rather than given a
    # made-up one.
    assert (await tools.run("get_quote", {}, cart))["error"] == "operator_confirmation_required"

    assert "error" in await tools.run("submit_sales_request", {"district_id": 1}, cart)

    sent = await tools.run(
        "submit_sales_request",
        {
            "name": "Akmal",
            "phone": "+998901234567",
            "district_id": user.district_id,
            "address": "Chilonzor 9-kvartal 12-uy",
        },
        cart,
    )
    assert sent.get("ok") is True and sent.get("handed_to_operator") is True, sent

    row = await test_session.get(SalesRequest, sent["request_id"])
    assert row is not None
    assert row.status == "open" and row.phone == "+998901234567"
    assert [item.canonical_id for item in row.items] == [unpriced.id]
    assert row.items[0].requires_confirmation is True
    assert row.items[0].reference_unit_price is None

    # An enquiry is not an order, and it empties the basket it was made from.
    assert (await test_session.scalar(select(func.count()).select_from(Order))) == 0
    assert not (await CartService(test_session).get(user.id)).lines
