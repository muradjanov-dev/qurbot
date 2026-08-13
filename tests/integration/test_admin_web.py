"""Integration tests for the Phase 8 admin web panel (SPEC §11).

Uses FastAPI's dependency_overrides to point the app's `get_db_session` at the
same `test_session` fixture connection used to seed fixtures, and real HTTP Basic
Auth credentials against the configured admin_basic_auth_user/password.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, ProductAlias, Unit
from app.db.models.ops import UnmatchedQuery
from app.db.models.shop import District, Shop, ShopProduct
from app.db.session import get_db_session
from app.main import app

AUTH = (settings.admin_basic_auth_user, settings.admin_basic_auth_password)


@pytest.fixture
def admin_client(test_session: AsyncSession) -> Iterator[TestClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db_session, None)


async def _make_canonical_product(session: AsyncSession) -> CanonicalProduct:
    unit = Unit(code="dona", name_uz="Dona", name_ru="Штука", dimension="count")
    category = Category(slug="test-cat", name_uz="Test", name_ru="Тест")
    session.add_all([unit, category])
    await session.flush()
    product = CanonicalProduct(
        slug="sement-m400",
        name_uz="Sement M400",
        name_uz_cyrl="Семент М400",
        name_ru="Цемент М400",
        category_id=category.id,
        base_unit_code=unit.code,
        search_doc="sement m400",
    )
    session.add(product)
    await session.flush()
    return product


@pytest.mark.asyncio
async def test_unmatched_requires_auth(admin_client: TestClient) -> None:
    response = admin_client.get("/admin/unmatched")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unmatched_list_and_create_alias(
    admin_client: TestClient, test_session: AsyncSession
) -> None:
    product = await _make_canonical_product(test_session)
    query = UnmatchedQuery(raw_text="shipr 8 tolali", normalized="shipr 8 tolali", occurrences=3)
    test_session.add(query)
    await test_session.flush()

    list_response = admin_client.get("/admin/unmatched", auth=AUTH)
    assert list_response.status_code == 200
    assert "shipr 8 tolali" in list_response.text

    create_response = admin_client.post(
        f"/admin/unmatched/{query.id}/create-alias",
        data={"canonical_id": product.id},
        auth=AUTH,
        follow_redirects=False,
    )
    assert create_response.status_code == 303

    await test_session.refresh(query)
    assert query.status == "resolved"
    assert query.resolved_alias_id is not None

    alias_stmt = select(ProductAlias).where(ProductAlias.id == query.resolved_alias_id)
    alias = (await test_session.execute(alias_stmt)).scalars().first()
    assert alias is not None
    assert alias.is_approved is True
    assert alias.canonical_id == product.id


@pytest.mark.asyncio
async def test_unmatched_mark_junk(admin_client: TestClient, test_session: AsyncSession) -> None:
    query = UnmatchedQuery(raw_text="???", normalized="???")
    test_session.add(query)
    await test_session.flush()

    response = admin_client.post(
        f"/admin/unmatched/{query.id}/mark-junk", auth=AUTH, follow_redirects=False
    )
    assert response.status_code == 303

    await test_session.refresh(query)
    assert query.status == "junk"


@pytest.mark.asyncio
async def test_alias_approve_and_reject(
    admin_client: TestClient, test_session: AsyncSession
) -> None:
    product = await _make_canonical_product(test_session)
    alias_to_approve = ProductAlias(
        canonical_id=product.id,
        alias_norm="sement m-400",
        alias_raw="sement m-400",
        source="llm",
        confidence=Decimal("0.9"),
        is_approved=False,
    )
    alias_to_reject = ProductAlias(
        canonical_id=product.id,
        alias_norm="junk alias",
        alias_raw="junk alias",
        source="llm",
        confidence=Decimal("0.3"),
        is_approved=False,
    )
    test_session.add_all([alias_to_approve, alias_to_reject])
    await test_session.flush()

    list_response = admin_client.get("/admin/aliases", auth=AUTH)
    assert list_response.status_code == 200
    assert "sement m-400" in list_response.text

    approve_response = admin_client.post(
        f"/admin/aliases/{alias_to_approve.id}/approve", auth=AUTH, follow_redirects=False
    )
    assert approve_response.status_code == 303
    await test_session.refresh(alias_to_approve)
    assert alias_to_approve.is_approved is True

    reject_response = admin_client.post(
        f"/admin/aliases/{alias_to_reject.id}/reject", auth=AUTH, follow_redirects=False
    )
    assert reject_response.status_code == 303
    reject_stmt = select(ProductAlias).where(ProductAlias.id == alias_to_reject.id)
    remaining = (await test_session.execute(reject_stmt)).scalars().first()
    assert remaining is None


@pytest.mark.asyncio
async def test_shop_verify_and_deactivate(
    admin_client: TestClient, test_session: AsyncSession
) -> None:
    district = District(name_uz="Chilonzor", name_ru="Чиланзар")
    test_session.add(district)
    await test_session.flush()
    shop = Shop(name="Test Shop", phone="+998901112233", district_id=district.id, address="addr")
    test_session.add(shop)
    await test_session.flush()

    list_response = admin_client.get("/admin/shops", auth=AUTH)
    assert list_response.status_code == 200
    assert "Test Shop" in list_response.text

    verify_response = admin_client.post(
        f"/admin/shops/{shop.id}/verify", auth=AUTH, follow_redirects=False
    )
    assert verify_response.status_code == 303
    await test_session.refresh(shop)
    assert shop.verified_at is not None

    deactivate_response = admin_client.post(
        f"/admin/shops/{shop.id}/deactivate", auth=AUTH, follow_redirects=False
    )
    assert deactivate_response.status_code == 303
    await test_session.refresh(shop)
    assert shop.is_active is False


@pytest.mark.asyncio
async def test_offers_filter_and_bulk_deactivate(
    admin_client: TestClient, test_session: AsyncSession
) -> None:
    district = District(name_uz="Yunusobod", name_ru="Юнусабад")
    test_session.add(district)
    await test_session.flush()
    shop = Shop(name="Offer Shop", phone="+998907778899", district_id=district.id, address="addr")
    test_session.add(shop)
    await test_session.flush()
    offer = ShopProduct(
        shop_id=shop.id,
        raw_name="Sement M400",
        raw_unit="qop",
        price_per_pack=Decimal("55000.00"),
        price_per_base_unit=Decimal("1100.0000"),
        staleness_state="stale",
    )
    test_session.add(offer)
    await test_session.flush()

    filtered_response = admin_client.get("/admin/offers?state=stale", auth=AUTH)
    assert filtered_response.status_code == 200
    assert "Sement M400" in filtered_response.text

    deactivate_response = admin_client.post(
        "/admin/offers/bulk-deactivate",
        data={"offer_ids": [offer.id]},
        auth=AUTH,
        follow_redirects=False,
    )
    assert deactivate_response.status_code == 303
    await test_session.refresh(offer)
    assert offer.is_active is False


@pytest.mark.asyncio
async def test_dashboard_and_llm_cost_render_empty(admin_client: TestClient) -> None:
    dashboard_response = admin_client.get("/admin/dashboard", auth=AUTH)
    assert dashboard_response.status_code == 200

    llm_cost_response = admin_client.get("/admin/llm-cost", auth=AUTH)
    assert llm_cost_response.status_code == 200


@pytest.mark.asyncio
async def test_admin_root_redirects_to_unmatched(admin_client: TestClient) -> None:
    response = admin_client.get("/admin", auth=AUTH, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/admin/unmatched"
