"""Manual baskets stay owned, atomic, replay-safe and outside fulfillment."""

from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.models.catalog import CanonicalProduct
from app.db.models.conversation import Conversation
from app.db.models.order import Order
from app.db.models.sales_request import SalesRequest, SalesRequestItem
from app.db.models.user import User
from app.services.cart_service import CartConflict, CartService
from app.services.sales_request_service import SalesRequestService, contact_defaults
from app.web.storefront.session import SESSION_COOKIE, sign_session
from tests.integration.test_storefront_web import _seed
from tests.integration.test_visitor_operator import bootstrap, headers, web  # noqa: F401


async def basket(client, session):
    fixture = await _seed(session)
    original = await session.get(CanonicalProduct, fixture.product_id)
    products = [original]
    for thickness in [3, 4]:
        product = CanonicalProduct(
            slug=f"manual-{thickness}",
            name_uz=f"Fanera {thickness} mm",
            name_ru=f"Фанера {thickness} мм",
            name_uz_cyrl=f"Фанера {thickness} мм",
            category_id=original.category_id,
            base_unit_code="dona",
            search_doc=f"fanera {thickness}",
            attributes={"price_on_request": True, "stock_unverified": True, "thickness": thickness},
        )
        session.add(product)
        products.append(product)
    await session.commit()
    await bootstrap(client)
    revision = 0
    for product in products:
        result = await client.put(
            f"/api/cart/items/{product.id}",
            headers=headers(client),
            json={"qty": "155", "unit_code": "dona", "expected_revision": revision},
        )
        assert result.status_code == 200, result.text
        revision = result.json()["revision"]
    owner = (await client.get("/api/chat")).json()["conversation_id"]
    conversation = await session.get(Conversation, owner)
    return (
        {
            "contact_name": "Test customer",
            "phone": "+998901234567",
            "address_text": "Test street 155",
            "district_id": (await session.get(User, fixture.user_id)).district_id,
            "cart_revision": revision,
            "idempotency_key": "manual-155",
        },
        products,
        conversation,
    )


@pytest.mark.parametrize("outcome", ["agreed", "cancelled"])
async def test_mixed_cart_request_and_operator_lifecycle(web, test_session, outcome):  # noqa: F811
    client, app = web
    body, products, conversation = await basket(client, test_session)
    cart = (await client.get("/api/cart")).json()
    assert len(cart["lines"]) == 3 and cart["requires_confirmation"]
    assert [line["qty"] for line in cart["lines"]] == ["155"] * 3
    denied = await client.post(
        "/api/order", json={**body, "expected_total": "0"}, headers=headers(client)
    )
    assert denied.json()["requires_confirmation"]
    assert (await client.post("/api/sales-requests", json=body)).status_code == 403
    response = await client.post("/api/sales-requests", json=body, headers=headers(client))
    assert response.status_code == 200, response.text
    enquiry = response.json()["request"]
    assert enquiry["status"] == "open" and len(enquiry["items"]) == 3
    assert enquiry["items"][0]["reference_unit_price"] is not None
    assert all(line["reference_unit_price"] is None for line in enquiry["items"][1:])
    repeated = await client.post("/api/sales-requests", json=body, headers=headers(client))
    assert repeated.json()["request"]["id"] == enquiry["id"]
    assert not (await client.get("/api/cart")).json()["lines"]
    assert await test_session.scalar(select(func.count()).select_from(Order)) == 0
    assert await test_session.scalar(select(func.count()).select_from(SalesRequest)) == 1
    assert await test_session.scalar(select(func.count()).select_from(SalesRequestItem)) == 3
    assert (await client.get("/sales-requests")).status_code == 200
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://shop.test") as other:
        await bootstrap(other)
        assert (await other.get(f"/api/sales-requests/{enquiry['id']}")).status_code == 404
        assert not (await other.get("/api/sales-requests")).json()["requests"]
        assert (
            await other.post(
                f"/api/chat/operator/sales-requests/{enquiry['id']}/resolve",
                json={"outcome": outcome, "note": "Intruder"},
                headers=headers(other),
            )
        ).status_code == 403
    admins = [User(tg_id=90001, role="admin"), User(tg_id=90002, role="admin")]
    test_session.add_all(admins)
    await test_session.commit()
    # Reload: a rejected HTTP request may have rolled back its identity map.
    admin_id, tg_id, loser_id, loser_tg = (
        admins[0].id,
        admins[0].tg_id,
        admins[1].id,
        admins[1].tg_id,
    )
    conversation_id = enquiry["conversation_id"]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.test"
    ) as operator:
        operator.cookies.set(SESSION_COOKIE, sign_session(user_id=admin_id, tg_id=tg_id))
        assert (
            await operator.post(
                f"/api/chat/operator/{conversation_id}/claim", json={}, headers=headers(operator)
            )
        ).status_code == 200
        cards = (await operator.get(f"/api/chat/operator/{conversation_id}/sales-requests")).json()
        assert cards["requests"][0]["phone"] == body["phone"]
        assert (
            await operator.post(
                f"/api/chat/operator/{conversation_id}/close", json={}, headers=headers(operator)
            )
        ).status_code == 409
        endpoint = f"/api/chat/operator/sales-requests/{enquiry['id']}/resolve"
        assert (
            await operator.post(
                endpoint, json={"outcome": outcome, "note": " "}, headers=headers(operator)
            )
        ).status_code == 422
        operator.cookies.set(SESSION_COOKIE, sign_session(user_id=loser_id, tg_id=loser_tg))
        assert (
            await operator.post(
                endpoint, json={"outcome": outcome, "note": "No"}, headers=headers(operator)
            )
        ).status_code == 409
        operator.cookies.set(SESSION_COOKIE, sign_session(user_id=admin_id, tg_id=tg_id))
        for _ in range(2):
            resolved = await operator.post(
                endpoint,
                json={"outcome": outcome, "note": "Customer contacted"},
                headers=headers(operator),
            )
            assert resolved.status_code == 200, resolved.text
        assert (
            await operator.post(
                f"/api/chat/operator/{conversation_id}/close", json={}, headers=headers(operator)
            )
        ).status_code == 200
    history = (await client.get("/api/sales-requests")).json()["requests"][0]
    assert history["status"] == outcome and history["resolution_note"] == "Customer contacted"
    assert await test_session.scalar(select(func.count()).select_from(Order)) == 0


async def test_unknown_request_revision_replay_and_new_cart(web, test_session):  # noqa: F811
    client, _ = web
    body, products, conversation = await basket(client, test_session)
    user = await test_session.get(User, conversation.user_id)
    service = SalesRequestService(test_session)
    kwargs = dict(
        revision=body["cart_revision"],
        key="one",
        name=body["contact_name"],
        phone=body["phone"],
        district_id=body["district_id"],
        address=body["address_text"],
        channel="telegram",
    )
    with pytest.raises(CartConflict):
        await service.create(user, **{**kwargs, "revision": 0})
    row = await service.create(user, **kwargs)
    first_id = row.id
    assert conversation.status == "waiting"
    await test_session.commit()
    cart = await CartService(test_session).get(user.id)
    added = await CartService(test_session).set_item(
        user.id, products[1].id, "200", expected_revision=cart.revision
    )
    assert (await service.create(user, **kwargs)).id == first_id
    assert (await CartService(test_session).get(user.id)).lines[0]["qty"] == "200"
    second = await service.create(user, **{**kwargs, "key": "two", "revision": added.revision})
    assert len(second.items) == 1 and second.items[0].qty == Decimal("200")
    assert second.items[0].reference_unit_price is None
    await test_session.commit()
    assert (await contact_defaults(test_session, user))["address"] == body["address_text"]
    assert await test_session.scalar(select(func.count()).select_from(Order)) == 0


async def test_optional_request_pin_is_visible_to_the_assigned_operator(web, test_session):  # noqa: F811
    client, app = web
    body, _, conversation = await basket(client, test_session)
    with_pin = {**body, "lat": "41.2500000", "lng": "69.2000000"}
    response = await client.post("/api/sales-requests", json=with_pin, headers=headers(client))
    assert response.status_code == 200, response.text
    request = response.json()["request"]
    assert request["lat"] == 41.25 and request["lng"] == 69.2
    stored = await test_session.get(SalesRequest, request["id"])
    assert stored is not None and stored.conversation_id == conversation.id
    assert stored.lat == Decimal("41.25") and stored.lng == Decimal("69.2")

    admin = User(tg_id=887711, role="admin", full_name="Operator")
    test_session.add(admin)
    await test_session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://shop.test"
    ) as operator:
        operator.cookies.set(SESSION_COOKIE, sign_session(user_id=admin.id, tg_id=admin.tg_id))
        rows = await operator.get(f"/api/chat/operator/{conversation.id}/sales-requests")
        assert rows.status_code == 200
        assert rows.json()["requests"][0]["lat"] == 41.25
        assert rows.json()["requests"][0]["lng"] == 69.2
