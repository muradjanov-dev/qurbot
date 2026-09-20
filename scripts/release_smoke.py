"""Exercise real HTTP handlers and PostgreSQL, rolling back ALL fixture writes.

Run in the release container: python -m scripts.release_smoke
No lifespan, Telegram, geocoder, or paid AI calls. The outer DB transaction
survives endpoint commits via savepoints; nothing reaches fulfillment/metrics.
Sequence numbers can advance, as with any rolled-back PostgreSQL insert.
"""

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import settings
from app.db.models import (
    CanonicalProduct,
    Category,
    District,
    Order,
    ShopDeliveryRule,
    ShopProduct,
    User,
)
from app.db.models.sales_request import SalesRequest
from app.db.models.user import VisitorSession
from app.db.session import engine, get_db_session
from app.main import create_app
from app.services.house_shop import get_house_shop
from app.web.storefront.security import csrf_token
from app.web.storefront.session import GUEST_COOKIE, SESSION_COOKIE, sign_session


async def run(guest: bool = False) -> dict[str, object]:
    marker = f"release-probe-{uuid4().hex}"
    test_tg_id = -900000001
    settings.llm_enabled = False
    settings.agent_enabled = False
    settings.test_tg_ids = [*settings.test_tg_ids, test_tg_id]
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                category = await session.scalar(
                    select(Category)
                    .where(Category.slug.in_(settings.enabled_category_slugs))
                    .limit(1)
                )
                assert category is not None, "seeded enabled category required"
                district = District(region="Release test", name_uz=marker, name_ru=marker)
                session.add(district)
                await session.flush()
                shop = await get_house_shop(session)
                assert shop is not None
                product = CanonicalProduct(
                    slug=marker,
                    name_uz=marker,
                    name_uz_cyrl=marker,
                    name_ru=marker,
                    category_id=category.id,
                    base_unit_code="dona",
                    search_doc=marker,
                )
                user = User(
                    tg_id=None if guest else test_tg_id,
                    full_name="ROLLBACK release probe",
                    district_id=district.id,
                    is_test=True,
                )
                session.add_all([product, user])
                await session.flush()
                session.add_all(
                    [
                        ShopProduct(
                            shop_id=shop.id,
                            canonical_id=product.id,
                            raw_name=marker,
                            raw_unit="dona",
                            pack_size=Decimal("1"),
                            pack_unit_code="dona",
                            price_per_pack=Decimal("10000"),
                            price_per_base_unit=Decimal("10000"),
                            stock_status="in_stock",
                            stock_qty=Decimal("10"),
                            staleness_state="fresh",
                        ),
                        ShopDeliveryRule(
                            shop_id=shop.id,
                            district_id=district.id,
                            fee=Decimal("5000"),
                            min_order=Decimal("0"),
                            eta_hours=24,
                        ),
                    ]
                )
                await session.commit()

                async def db() -> AsyncIterator[AsyncSession]:
                    yield session

                app = create_app()
                app.dependency_overrides[get_db_session] = db
                cookie_name = SESSION_COOKIE
                if guest:
                    cookie_name = GUEST_COOKIE
                    cookie = secrets.token_urlsafe(32)
                    session.add(
                        VisitorSession(
                            token_hash=sha256(cookie.encode()).hexdigest(),
                            user_id=user.id,
                            expires_at=datetime.now(UTC) + timedelta(hours=1),
                        )
                    )
                    await session.commit()
                else:
                    cookie = sign_session(user_id=user.id, tg_id=test_tg_id)
                request = Request(
                    {
                        "type": "http",
                        "headers": [(b"cookie", f"{cookie_name}={cookie}".encode())],
                    }
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://release.test",
                    cookies={cookie_name: cookie},
                    headers={"X-CSRF-Token": csrf_token(request)},
                ) as client:
                    page = await client.get(f"/product/{product.id}")
                    assert page.status_code == 200 and marker in page.text
                    current = (await client.get("/api/cart")).json()
                    added = (
                        await client.put(
                            f"/api/cart/items/{product.id}",
                            json={
                                "qty": "2",
                                "unit_code": "dona",
                                "expected_revision": current["revision"],
                            },
                        )
                    ).json()
                    assert added["ok"], added
                    quote = (await client.post("/api/quote", json={"lines": added["lines"]})).json()
                    assert quote["ok"], quote
                    variant = quote["variants"][0]
                    assert Decimal(variant["grand_total_raw"]) == Decimal("25000")
                    body = {
                        "contact_name": "ROLLBACK test customer",
                        "district_id": district.id,
                        "phone": "+998900000000",
                        "address_text": "ROLLBACK release test address",
                        "expected_total": "1",
                        "cart_revision": added["revision"],
                        "idempotency_key": marker,
                        "strategy": variant["strategy"],
                    }
                    changed = (await client.post("/api/order", json=body)).json()
                    assert changed.get("price_changed"), changed
                    body["expected_total"] = variant["grand_total_raw"]
                    placed = (await client.post("/api/order", json=body)).json()
                    assert placed["ok"], placed
                    repeated = (await client.post("/api/order", json=body)).json()
                    assert repeated["ok"] and repeated["order_id"] == placed["order_id"], repeated
                    order = await session.get(Order, placed["order_id"])
                    assert order is not None and order.is_test
                    empty = (await client.get("/api/cart")).json()
                    assert not empty["lines"]

                    # New manual flow: immutable mixed basket, not another order.
                    unknown = CanonicalProduct(
                        slug=marker + "-unknown",
                        name_uz="Test fanera 4 mm",
                        name_uz_cyrl="Тест фанера 4 мм",
                        name_ru="Тест фанера 4 мм",
                        category_id=category.id,
                        base_unit_code="dona",
                        search_doc=marker,
                        attributes={"price_on_request": True, "stock_unverified": True},
                    )
                    operator = User(
                        tg_id=-900000002, full_name="ROLLBACK operator", role="admin", is_test=True
                    )
                    session.add_all([unknown, operator])
                    await session.commit()
                    for product_id in (product.id, unknown.id):
                        current = (await client.get("/api/cart")).json()
                        updated = await client.put(
                            f"/api/cart/items/{product_id}",
                            json={
                                "qty": "155",
                                "unit_code": "dona",
                                "expected_revision": current["revision"],
                            },
                        )
                        assert updated.status_code == 200, updated.text
                    manual = {
                        **body,
                        "idempotency_key": marker + "-manual",
                        "cart_revision": updated.json()["revision"],
                    }
                    preview = (await client.post("/api/checkout/preview", json=manual)).json()
                    assert preview["requires_confirmation"], preview
                    submitted = (await client.post("/api/sales-requests", json=manual)).json()
                    assert submitted["ok"], submitted
                    enquiry = submitted["request"]
                    repeated = (await client.post("/api/sales-requests", json=manual)).json()
                    assert repeated["request"]["id"] == enquiry["id"]
                    assert (
                        len(enquiry["items"]) == 2
                        and enquiry["items"][1]["reference_unit_price"] is None
                    )
                    assert (await session.get(SalesRequest, enquiry["id"])).is_test
                    assert not (await client.get("/api/cart")).json()["lines"]
                    operator_cookie = sign_session(user_id=operator.id, tg_id=operator.tg_id)
                    op_request = Request(
                        {
                            "type": "http",
                            "headers": [
                                (b"cookie", f"{SESSION_COOKIE}={operator_cookie}".encode())
                            ],
                        }
                    )
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://release.test",
                        cookies={SESSION_COOKIE: operator_cookie},
                        headers={"X-CSRF-Token": csrf_token(op_request)},
                    ) as admin_client:
                        prefix = f"/api/chat/operator/{enquiry['conversation_id']}"
                        assert (
                            await admin_client.post(prefix + "/claim", json={})
                        ).status_code == 200
                        assert (
                            await admin_client.post(prefix + "/close", json={})
                        ).status_code == 409
                        resolved = await admin_client.post(
                            f"/api/chat/operator/sales-requests/{enquiry['id']}/resolve",
                            json={
                                "outcome": "agreed",
                                "note": "ROLLBACK synthetic check; no fulfillment",
                            },
                        )
                        assert resolved.status_code == 200, resolved.text
                        assert (
                            await admin_client.post(prefix + "/close", json={})
                        ).status_code == 200
                    history = (await client.get("/api/sales-requests")).json()["requests"]
                    assert history[0]["status"] == "agreed"
                    assert (
                        len(
                            (
                                await session.scalars(select(Order).where(Order.user_id == user.id))
                            ).all()
                        )
                        == 1
                    )
        finally:
            await transaction.rollback()
    async with AsyncSession(engine) as verify:
        assert (
            await verify.scalar(select(CanonicalProduct.id).where(CanonicalProduct.slug == marker))
            is None
        )
    await engine.dispose()
    return {
        "ok": True,
        "actor": "guest" if guest else "telegram",
        "rollback_verified": True,
        "checks": [
            "product",
            "cart",
            "live_quote",
            "reconfirm_price",
            "confirm",
            "idempotent_order",
            "test_order",
            "cart_clear",
            "manual_mixed_cart",
            "idempotent_request",
            "operator_resolution",
            "customer_request_history",
            "manual_request_no_extra_order",
        ],
        "paid_ai_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run())))
    print(json.dumps(asyncio.run(run(guest=True))))
