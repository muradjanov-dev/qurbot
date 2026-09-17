"""Cart durability, retry receipts, bot parity and safe checkout boundaries."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.bot.handlers.customer import _load_durable_cart, _persist_bot_cart
from app.core.config import settings
from app.db.models.cart import CheckoutAttempt
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.ops import Event, PebbleAward
from app.db.models.order import Order
from app.db.models.shop import District, Shop, ShopDeliveryRule, ShopProduct
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.order_repo import OrderRepository
from app.db.session import get_db_session
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.services.order_service import notify_order
from app.web.storefront.routers import cart, checkout
from app.web.storefront.security import csrf_token
from app.web.storefront.session import SESSION_COOKIE, sign_session


@pytest.fixture
async def seeded(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> tuple[User, CanonicalProduct, ShopProduct]:
    monkeypatch.setattr(settings, "enabled_category_slugs", [])
    monkeypatch.setattr(settings, "llm_enabled", False)
    test_session.add(Unit(code="dona", name_uz="Dona", name_ru="Штука", dimension="count"))
    category = Category(slug="cart-fixture", name_uz="Test", name_ru="Test")
    user = User(tg_id=701, full_name="Cart test")
    district = District(region="Test", name_uz="Test", name_ru="Test")
    test_session.add(district)
    await test_session.flush()
    shop = Shop(
        name=settings.house_shop_name,
        phone=settings.house_shop_phone,
        district_id=district.id,
        address="Test",
    )
    test_session.add_all([category, user, shop])
    await test_session.flush()
    product = CanonicalProduct(
        slug="cart-fixture",
        name_uz="Test",
        name_uz_cyrl="Тест",
        name_ru="Тест",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="test",
    )
    test_session.add(product)
    await test_session.flush()
    test_session.add(
        ShopDeliveryRule(
            shop_id=shop.id,
            district_id=None,
            fee=Decimal("0"),
            min_order=Decimal("0"),
            eta_hours=24,
        )
    )
    offer = ShopProduct(
        shop_id=shop.id,
        canonical_id=product.id,
        raw_name="Test",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("10000"),
        price_per_base_unit=Decimal("10000"),
        stock_status="in_stock",
        staleness_state="fresh",
    )
    test_session.add(offer)
    await test_session.commit()
    return user, product, offer


@pytest.fixture
async def client(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct]
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(cart.router)
    app.include_router(checkout.router)

    async def session_override() -> AsyncIterator[AsyncSession]:
        try:
            yield test_session
            await test_session.commit()
        except Exception:
            await test_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = session_override
    user = seeded[0]
    cookie = sign_session(user_id=user.id, tg_id=user.tg_id)
    request = Request(
        {"type": "http", "headers": [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())]}
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        cookies={SESSION_COOKIE: cookie},
        headers={"X-CSRF-Token": csrf_token(request)},
    ) as http:
        yield http


async def test_cart_conflicts_and_durability(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct]
) -> None:
    user, product, _ = seeded
    service = CartService(test_session)
    first = await service.set_item(user.id, product.id, "2.5", expected_revision=0)
    await test_session.commit()
    with pytest.raises(CartConflict):
        await service.set_item(user.id, product.id, "99", expected_revision=0)
    current = await CartService(test_session).get(user.id)
    assert current.revision == first.revision
    assert current.lines[0]["qty"] == "2.5"
    unchanged = await service.set_item(user.id, product.id, "2.5", expected_revision=first.revision)
    assert unchanged.revision == first.revision


async def test_merge_max_and_retry_does_not_resurrect(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct]
) -> None:
    user, product, _ = seeded
    service = CartService(test_session)
    initial = await service.set_item(user.id, product.id, "5", expected_revision=0)
    lines = [{"canonical_id": product.id, "qty": "3"}, {"canonical_id": product.id, "qty": "8"}]
    merged = await service.merge(
        user.id, lines, merge_key="guest:test", expected_revision=initial.revision
    )
    assert merged.lines[0]["qty"] == "8"
    cleared = await service.clear(user.id, expected_revision=merged.revision)
    await test_session.commit()
    replay = await service.merge(
        user.id, lines, merge_key="guest:test", expected_revision=initial.revision
    )
    assert replay.lines == ()
    assert replay.revision == cleared.revision


@pytest.mark.parametrize("qty", ["NaN", "Infinity", "-1", "1000001", "0.0000001", True])
async def test_invalid_quantity_is_not_persisted(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct], qty: object
) -> None:
    user, product, _ = seeded
    with pytest.raises(InvalidCartItem):
        await CartService(test_session).set_item(user.id, product.id, qty, expected_revision=0)
    assert (await CartService(test_session).get(user.id)).lines == ()


async def test_legacy_sources_import_once_and_bot_reads_web(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct]
) -> None:
    user, product, _ = seeded
    service = CartService(test_session)
    data = {
        "basket_lines": [{"canonical_id": product.id, "qty": "2", "unit_code": "dona"}],
        "agent": {"basket": [{"canonical_id": product.id, "qty": "4", "unit_code": "dona"}]},
    }
    merged = await service.migrate_legacy(user.id, data)
    assert merged.lines[0]["qty"] == "4"
    empty = await service.clear(user.id, expected_revision=merged.revision)
    assert (await service.migrate_legacy(user.id, data)).revision == empty.revision
    state = FSMContext(
        MemoryStorage(), StorageKey(bot_id=1, chat_id=user.tg_id, user_id=user.tg_id)
    )
    web = await service.set_item(user.id, product.id, "7", expected_revision=empty.revision)
    bot_lines = await _load_durable_cart(state, test_session)
    assert bot_lines[0]["qty"] == "7"
    await service.set_item(user.id, product.id, "9", expected_revision=web.revision)
    bot_lines[0]["qty"] = "20"
    assert not await _persist_bot_cart(state, test_session, bot_lines)
    assert (await service.get(user.id)).lines[0]["qty"] == "9"


async def test_cart_api_csrf_conflict_and_user_isolation(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded: tuple[User, CanonicalProduct, ShopProduct],
) -> None:
    user, product, _ = seeded
    user_id, product_id = user.id, product.id
    denied = await client.put(
        f"/api/cart/items/{product_id}",
        json={"qty": "2", "expected_revision": 0},
        headers={"X-CSRF-Token": "wrong"},
    )
    assert denied.status_code == 403
    added = await client.put(
        f"/api/cart/items/{product_id}", json={"qty": "2", "expected_revision": 0}
    )
    assert added.status_code == 200
    conflict = await client.delete(f"/api/cart/items/{product_id}?expected_revision=0")
    assert conflict.status_code == 409
    assert conflict.json()["lines"][0]["qty"] == "2"
    second = User(tg_id=702)
    test_session.add(second)
    await test_session.commit()
    client.cookies.set(SESSION_COOKIE, sign_session(user_id=second.id, tg_id=second.tg_id))
    assert (await client.get("/api/cart")).json()["lines"] == []
    assert (await CartService(test_session).get(user_id)).lines[0]["qty"] == "2"


async def _checkout_body(client: AsyncClient, product: CanonicalProduct) -> dict[str, object]:
    result = await client.put(
        f"/api/cart/items/{product.id}", json={"qty": "2", "expected_revision": 0}
    )
    assert result.status_code == 200
    return {
        "cart_revision": result.json()["revision"],
        "idempotency_key": "checkout-test",
        "expected_total": "20000",
        "phone": "+998901234567",
        "address_text": "Test delivery",
    }


async def test_checkout_retry_one_order_reward_and_atomic_clear(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded: tuple[User, CanonicalProduct, ShopProduct],
) -> None:
    user, product, _ = seeded
    body = await _checkout_body(client, product)
    first = await client.post("/api/order", json=body)
    assert first.json()["ok"], first.text
    replay = await client.post("/api/order", json=body)
    assert replay.json()["order_id"] == first.json()["order_id"]
    assert replay.json()["replayed"]
    assert await test_session.scalar(select(func.count(Order.id))) == 1
    assert await test_session.scalar(select(func.count()).select_from(CheckoutAttempt)) == 1
    assert await test_session.scalar(select(func.count(PebbleAward.id))) == 1
    confirmations = (
        await test_session.scalars(select(Event).where(Event.name == "checkout_confirmed"))
    ).all()
    assert len(confirmations) == 1
    assert set(confirmations[0].props) == {"order_id", "source", "cart_revision"}
    assert (await CartService(test_session).get(user.id)).lines == ()
    changed = await client.post("/api/order", json={**body, "phone": "+998901234568"})
    assert changed.status_code == 409


async def test_checkout_reprice_stock_and_revision_refuse_order(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded: tuple[User, CanonicalProduct, ShopProduct],
) -> None:
    user, product, offer = seeded
    body = await _checkout_body(client, product)
    offer.price_per_pack = Decimal("12000")
    offer.price_per_base_unit = Decimal("12000")
    await test_session.commit()
    repriced = await client.post("/api/order", json=body)
    assert repriced.json()["price_changed"]
    assert Decimal(repriced.json()["variant"]["grand_total_raw"]) == Decimal("24000")
    offer.stock_status = "out"
    await test_session.commit()
    assert not (await client.post("/api/order", json={**body, "expected_total": "24000"})).json()[
        "ok"
    ]
    await CartService(test_session).set_item(
        user.id, product.id, "3", expected_revision=int(str(body["cart_revision"]))
    )
    await test_session.commit()
    assert (await client.post("/api/order", json=body)).status_code == 409
    assert await test_session.scalar(select(func.count(Order.id))) == 0


async def test_test_order_excluded_from_fulfillment_rewards_and_metrics(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded: tuple[User, CanonicalProduct, ShopProduct],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, product, _ = seeded
    monkeypatch.setattr(settings, "test_tg_ids", [user.tg_id])
    body = await _checkout_body(client, product)
    response = await client.post("/api/order", json=body)
    assert response.json()["ok"], response.text
    order = await test_session.get(Order, response.json()["order_id"])
    assert order is not None and order.is_test
    assert await test_session.scalar(select(func.count(PebbleAward.id))) == 0
    assert (
        await test_session.scalar(select(func.count(Event.id)).where(Event.name == "order_created"))
        == 0
    )
    now = datetime.now(UTC)
    assert await OpsRepository(test_session).get_order_stats(
        now - timedelta(days=1), now + timedelta(days=1)
    ) == (0, Decimal("0"))
    repo = OrderRepository(test_session)
    assert await repo.list_unconfirmed_before(now + timedelta(days=1)) == []
    part = order.shop_parts[0]
    assert await repo.get_shop_part(part.id) is None
    assert await repo.update_shop_response(part.id, "accepted") is None
    assert await repo.list_parts_for_shop(part.shop_id) == []
    from app.services.order_service import PlacedOrder

    bot = AsyncMock()
    await notify_order(bot, test_session, PlacedOrder(order=order, pebbles=0, parts=()), user=user)
    bot.send_message.assert_not_called()
    events = (await test_session.scalars(select(Event))).all()
    assert {event.name for event in events} == {
        "test_cart_updated",
        "test_order_created",
        "test_checkout_confirmed",
    }
    for event in events:
        assert not {"phone", "address", "raw_text", "idempotency_key"}.intersection(event.props)


async def test_merge_is_atomic_and_preserves_units(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct]
) -> None:
    user, product, _ = seeded
    service = CartService(test_session)
    initial = await service.set_item(user.id, product.id, "2", expected_revision=0, unit_code="qop")
    with pytest.raises(InvalidCartItem, match="unit_conflict"):
        await service.merge(
            user.id,
            [{"canonical_id": product.id, "qty": "9", "unit_code": "dona"}],
            merge_key="guest:units",
            expected_revision=initial.revision,
        )
    assert (await service.get(user.id)).lines[0]["unit_code"] == "qop"
    with pytest.raises(InvalidCartItem):
        await service.merge(
            user.id,
            [
                {"canonical_id": product.id, "qty": "8", "unit_code": "qop"},
                {"canonical_id": 999999, "qty": "1"},
            ],
            merge_key="guest:atomic",
            expected_revision=initial.revision,
        )
    assert (await service.get(user.id)).lines[0]["qty"] == "2"
    updates = (await test_session.scalars(select(Event).where(Event.name == "cart_updated"))).all()
    assert len(updates) == 1
    assert updates[0].props == {"revision": initial.revision, "items": 1}


@pytest.mark.parametrize("total", [None, "NaN", "Infinity", "not-a-number"])
async def test_checkout_requires_finite_explicit_total(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded: tuple[User, CanonicalProduct, ShopProduct],
    total: str | None,
) -> None:
    body = await _checkout_body(client, seeded[1])
    response = await client.post("/api/order", json={**body, "expected_total": total})
    assert not response.json()["ok"]
    assert await test_session.scalar(select(func.count(Order.id))) == 0


async def test_checkout_failure_rolls_back_cart_order_and_retry_receipt(
    client: AsyncClient,
    test_session: AsyncSession,
    seeded: tuple[User, CanonicalProduct, ShopProduct],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = seeded[0].id
    body = await _checkout_body(client, seeded[1])

    async def fail_award(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected reward write failure")

    with monkeypatch.context() as patch:
        patch.setattr(OpsRepository, "award_pebbles", fail_award)
        with pytest.raises(RuntimeError, match="injected"):
            await client.post("/api/order", json=body)
    assert await test_session.scalar(select(func.count(Order.id))) == 0
    assert await test_session.scalar(select(func.count()).select_from(CheckoutAttempt)) == 0
    restored = await CartService(test_session).get(user_id)
    assert restored.revision == body["cart_revision"]
    assert restored.lines[0]["qty"] == "2"
    assert (await client.post("/api/order", json=body)).json()["ok"]


async def test_cart_cannot_exceed_quote_line_limit(
    test_session: AsyncSession, seeded: tuple[User, CanonicalProduct, ShopProduct]
) -> None:
    user, first, _ = seeded
    products = [
        CanonicalProduct(
            slug=f"cart-cap-{index}",
            name_uz="Test",
            name_uz_cyrl="Тест",
            name_ru="Тест",
            category_id=first.category_id,
            base_unit_code="dona",
            search_doc="test",
        )
        for index in range(60)
    ]
    test_session.add_all(products)
    await test_session.flush()
    service = CartService(test_session)
    lines = [{"canonical_id": product.id, "qty": "1"} for product in products]
    full = await service.merge(user.id, lines, merge_key="guest:full", expected_revision=0)
    assert len(full.lines) == 60
    with pytest.raises(InvalidCartItem, match="cart_too_large"):
        await service.set_item(user.id, first.id, "1", expected_revision=full.revision)
    assert len((await service.get(user.id)).lines) == 60
    with pytest.raises(InvalidCartItem, match="cart_too_large"):
        await service.merge(
            user.id,
            [{"canonical_id": first.id, "qty": "1"}],
            merge_key="guest:over-limit",
            expected_revision=full.revision,
        )
    assert (await service.get(user.id)).revision == full.revision
