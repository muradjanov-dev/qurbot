"""Real row-lock races. Opt-in DB must be an isolated *_test or *_stage DB."""

import asyncio
import os
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models import CanonicalProduct, Category, Unit, User
from app.db.models.order import Basket, Order, OrderShopPart, Quote
from app.db.models.shop import District, Shop, ShopDeliveryRule, ShopProduct
from app.services.cart_service import CartConflict, CartService
from app.services.conversation_service import ConversationConflict, ConversationService
from app.services.order_service import place_order
from app.services.order_workflow import OrderWorkflowService, WorkflowError
from app.web.storefront.quoting import optimize, validate_lines


@pytest.fixture
async def pg_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("SALES_TEST_DATABASE_URL")
    if not url:
        pytest.skip("isolated PostgreSQL not configured")
    assert (make_url(url).database or "").endswith(("_test", "_stage")), "refuse non-test DB"
    schema = f"sales_test_{uuid4().hex}"
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(91827192)"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
    )
    monkeypatch.setattr(settings, "enabled_category_slugs", [])
    monkeypatch.setattr(settings, "admin_tg_ids", [])
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed(factory: async_sessionmaker[AsyncSession]) -> tuple[int, int, tuple[int, int]]:
    async with factory() as session:
        category = Category(slug="fixture", name_uz="Test", name_ru="Test")
        user = User(tg_id=-100, full_name="Test")
        admins = [User(tg_id=-101, role="admin"), User(tg_id=-102, role="admin")]
        session.add_all(
            [
                category,
                user,
                *admins,
                Unit(code="dona", name_uz="Dona", name_ru="Шт", dimension="count"),
            ]
        )
        await session.flush()
        product = CanonicalProduct(
            slug="fixture",
            name_uz="Test",
            name_uz_cyrl="Тест",
            name_ru="Тест",
            category_id=category.id,
            base_unit_code="dona",
            search_doc="test",
        )
        session.add(product)
        await session.flush()
        await session.commit()
        return user.id, product.id, (admins[0].id, admins[1].id)


@pytest.mark.asyncio
async def test_postgres_cart_first_creation_race(
    pg_sessions: async_sessionmaker[AsyncSession],
) -> None:
    user_id, product_id, _ = await seed(pg_sessions)

    async def update(qty: str) -> bool:
        async with pg_sessions() as session:
            try:
                await CartService(session).set_item(user_id, product_id, qty, expected_revision=0)
                await session.commit()
                return True
            except CartConflict:
                await session.rollback()
                return False

    assert sorted(await asyncio.gather(update("2"), update("3"))) == [False, True]
    async with pg_sessions() as session:
        snapshot = await CartService(session).get(user_id)
        assert snapshot.revision == 1 and len(snapshot.lines) == 1


@pytest.mark.asyncio
async def test_postgres_only_one_operator_claims(
    pg_sessions: async_sessionmaker[AsyncSession],
) -> None:
    user_id, _, admin_ids = await seed(pg_sessions)
    async with pg_sessions() as session:
        user = await session.get(User, user_id)
        assert user is not None
        conversation = await ConversationService(session).handoff(user)
        await session.commit()

    async def claim(admin_id: int) -> bool:
        async with pg_sessions() as session:
            admin = await session.get(User, admin_id)
            assert admin is not None
            try:
                await ConversationService(session).claim(admin, conversation["id"])
                await session.commit()
                return True
            except ConversationConflict:
                await session.rollback()
                return False

    assert sorted(await asyncio.gather(*(claim(admin_id) for admin_id in admin_ids))) == [
        False,
        True,
    ]


@pytest.mark.asyncio
async def test_postgres_double_checkout_one_order(
    pg_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, product_id, _ = await seed(pg_sessions)
    monkeypatch.setattr(settings, "test_tg_ids", [-100])
    async with pg_sessions() as session:
        district = District(region="Test", name_uz="Test", name_ru="Test")
        session.add(district)
        await session.flush()
        shop = Shop(
            name=settings.house_shop_name,
            phone="+998900000000",
            district_id=district.id,
            address="Test",
        )
        session.add(shop)
        await session.flush()
        session.add_all(
            [
                ShopProduct(
                    shop_id=shop.id,
                    canonical_id=product_id,
                    raw_name="Test",
                    raw_unit="dona",
                    pack_unit_code="dona",
                    pack_size=Decimal("1"),
                    price_per_pack=Decimal("10"),
                    price_per_base_unit=Decimal("10"),
                    stock_status="in_stock",
                    stock_qty=Decimal("10"),
                    staleness_state="fresh",
                ),
                ShopDeliveryRule(
                    shop_id=shop.id,
                    district_id=district.id,
                    fee=Decimal("0"),
                    min_order=Decimal("0"),
                    eta_hours=24,
                ),
            ]
        )
        await session.flush()
        snapshot = await CartService(session).set_item(
            user_id, product_id, "2", expected_revision=0
        )
        basket = await validate_lines(session, list(snapshot.lines))
        variants = await optimize(session, basket.items, district_id=district.id)
        assert variants and variants[0].is_orderable
        variant = variants[0]
        await session.commit()

    async def checkout() -> int:
        async with pg_sessions() as session:
            user = await session.get(User, user_id)
            assert user is not None
            placed = await place_order(
                session,
                user=user,
                variant=variant,
                contact_phone="+998900000000",
                delivery_address="Test address",
                idempotency_key="parallel-checkout",
                fingerprint="same-confirmation",
                cart_revision=snapshot.revision,
            )
            await session.commit()
            return placed.order.id

    ids = await asyncio.gather(checkout(), checkout())
    assert ids[0] == ids[1]


@pytest.mark.asyncio
async def test_postgres_parallel_manual_request_and_resolution(pg_sessions):
    from app.db.models.sales_request import SalesRequest
    from app.services.sales_request_service import SalesRequestService

    user_id, product_id, admin_ids = await seed(pg_sessions)
    async with pg_sessions() as session:
        district = District(region="Test", name_uz="Test", name_ru="Test")
        session.add(district)
        await session.flush()
        district_id = district.id
        await CartService(session).set_item(user_id, product_id, "155", expected_revision=0)
        await session.commit()

    async def submit():
        async with pg_sessions() as session:
            row = await SalesRequestService(session).create(
                await session.get(User, user_id),
                revision=1,
                key="parallel",
                name="Test",
                phone="+998900000000",
                district_id=district_id,
                address="Test address",
                channel="web",
            )
            await session.commit()
            return row.id, row.conversation_id

    results = await asyncio.wait_for(asyncio.gather(submit(), submit()), timeout=15)
    assert results[0] == results[1]
    request_id, conversation_id = results[0]
    async with pg_sessions() as session:
        assert not (await CartService(session).get(user_id)).lines
        await session.commit()  # Release cart lock before acquiring conversation lock.
        await ConversationService(session).claim(
            await session.get(User, admin_ids[0]), conversation_id
        )
        await session.commit()

    async def resolve(outcome):
        async with pg_sessions() as session:
            try:
                await SalesRequestService(session).resolve(
                    await session.get(User, admin_ids[0]), request_id, outcome, "Test result"
                )
                await session.commit()
                return True
            except ConversationConflict:
                await session.rollback()
                return False

    assert sorted(
        await asyncio.wait_for(asyncio.gather(resolve("agreed"), resolve("cancelled")), timeout=15)
    ) == [False, True]
    async with pg_sessions() as session:
        row = await session.get(SalesRequest, request_id)
        assert row.items[0].qty == Decimal("155") and row.items[0].reference_unit_price is None


@pytest.mark.asyncio
async def test_postgres_parallel_admins_reject_a_stale_order_snapshot(pg_sessions) -> None:
    user_id, _product_id, admin_ids = await seed(pg_sessions)
    async with pg_sessions() as session:
        district = District(region="Test", name_uz="Test", name_ru="Test")
        session.add(district)
        await session.flush()
        shop = Shop(
            name=settings.house_shop_name,
            phone="+998900000000",
            district_id=district.id,
            address="Test",
        )
        session.add(shop)
        await session.flush()
        basket = Basket(user_id=user_id, raw_text="test order", status="ordered")
        session.add(basket)
        await session.flush()
        quote = Quote(
            basket_id=basket.id,
            strategy="cheapest",
            items_total=Decimal("100"),
            delivery_total=Decimal("0"),
            grand_total=Decimal("100"),
            coverage_pct=Decimal("100"),
            shop_count=1,
        )
        session.add(quote)
        await session.flush()
        order = Order(
            quote_id=quote.id,
            user_id=user_id,
            status="new",
            contact_phone="+998900000000",
            delivery_address="Test address",
            grand_total_quoted=Decimal("100"),
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderShopPart(
                order_id=order.id,
                shop_id=shop.id,
                subtotal=Decimal("100"),
                delivery_fee=Decimal("0"),
                status="pending",
            )
        )
        await session.commit()
        order_id = order.id

    first_updated = asyncio.Event()
    second_attempting = asyncio.Event()
    second_error: list[WorkflowError] = []

    async def confirm_order() -> None:
        async with pg_sessions() as session:
            admin = await session.get(User, admin_ids[0])
            assert admin is not None
            await OrderWorkflowService(session).change_status(
                order_id, admin, "confirmed", 0, expected_status="new"
            )
            first_updated.set()
            await second_attempting.wait()
            await asyncio.sleep(0.05)
            await session.commit()

    async def cancel_from_stale_snapshot() -> None:
        async with pg_sessions() as session:
            admin = await session.get(User, admin_ids[1])
            stale_order = await session.get(Order, order_id)
            assert admin is not None and stale_order is not None
            assert stale_order.status == "new" and stale_order.workflow_revision == 0
            await first_updated.wait()
            second_attempting.set()
            try:
                await OrderWorkflowService(session).change_status(
                    order_id,
                    admin,
                    "cancelled",
                    0,
                    reason="Stale cancellation request",
                    expected_status="new",
                )
            except WorkflowError as exc:
                second_error.append(exc)
            finally:
                await session.rollback()

    await asyncio.wait_for(
        asyncio.gather(confirm_order(), cancel_from_stale_snapshot()), timeout=15
    )
    assert len(second_error) == 1
    assert second_error[0].code == "stale_revision"
    assert second_error[0].current_revision == 1
    async with pg_sessions() as session:
        persisted = await session.get(Order, order_id)
        assert persisted is not None
        assert persisted.status == "confirmed" and persisted.workflow_revision == 1
