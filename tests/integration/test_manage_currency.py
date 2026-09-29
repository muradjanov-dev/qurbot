"""Admin currency controls and source-currency offer editing."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fx import FxRateSetting
from app.db.models.shop import ShopProduct, ShopProductPriceTier
from app.domain.pricing.currency import convert_to_uzs
from tests.integration.test_storefront_web import _seed, _sign_in, _sign_in_admin
from tests.integration.test_storefront_web import client as storefront_client


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_currency_admin_guard_csrf_and_revision_conflict(
    client: TestClient, test_session: AsyncSession
) -> None:
    fixture = await _seed(test_session)
    guest = client.get("/manage/settings/currency", follow_redirects=False)
    assert guest.status_code == 303
    assert "/login?next=" in guest.headers["location"]

    _sign_in(client, fixture.user_id)
    assert client.get("/manage/settings/currency").status_code == 403
    assert (
        client.post(
            "/manage/settings/currency",
            data={"rate": "11820.48", "expected_revision": "0"},
        ).status_code
        == 403
    )

    admin = await _sign_in_admin(client, test_session)
    no_csrf = client.post(
        "/manage/settings/currency",
        data={"rate": "11820.48", "expected_revision": "0"},
        headers={"X-CSRF-Token": ""},
    )
    assert no_csrf.status_code == 403

    saved = client.post(
        "/manage/settings/currency",
        data={"rate": "11820.48", "expected_revision": "0"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    setting = await test_session.get(FxRateSetting, 1)
    assert setting is not None
    assert setting.usd_to_uzs_rate == Decimal("11820.480000")
    assert setting.revision == 1 and setting.updated_by == admin.id

    stale = client.post(
        "/manage/settings/currency",
        data={"rate": "12000", "expected_revision": "0"},
        follow_redirects=False,
    )
    assert stale.status_code == 409
    await test_session.refresh(setting)
    assert setting.usd_to_uzs_rate == Decimal("11820.480000")
    assert setting.revision == 1


@pytest.mark.asyncio
async def test_usd_offer_and_tier_save_and_explicit_currency_switch(
    client: TestClient, test_session: AsyncSession
) -> None:
    fixture = await _seed(test_session)
    await _sign_in_admin(client, test_session)
    rate = client.post(
        "/manage/settings/currency",
        data={"rate": "11820.48", "expected_revision": "0"},
        follow_redirects=False,
    )
    assert rate.status_code == 303

    offer = await test_session.scalar(
        select(ShopProduct).where(ShopProduct.shop_id == fixture.shop_id)
    )
    assert offer is not None
    response = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "pack_size": "1",
            "pack_unit_code": "dona",
            "source_price": "10.25",
            "source_currency": "USD",
            "confirm_currency_change": "true",
            "stock_status": "in_stock",
            "description": "",
            "active": "true",
            "tier_id": [""],
            "tier_min_qty": ["10"],
            "tier_source_price": ["9.75"],
            "tier_currency": ["USD"],
            "tier_currency_confirmed": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text

    await test_session.refresh(offer)
    assert offer.source_currency == "USD"
    assert offer.source_price_per_pack == Decimal("10.2500")
    assert offer.fx_rate_revision == 1
    assert offer.price_per_pack == convert_to_uzs(
        Decimal("10.25"), currency="USD", usd_to_uzs_rate=Decimal("11820.48")
    )
    tier = await test_session.scalar(
        select(ShopProductPriceTier).where(ShopProductPriceTier.shop_product_id == offer.id)
    )
    assert tier is not None
    assert tier.min_qty == Decimal("10.0000")
    assert tier.source_currency == "USD"
    assert tier.source_price_per_pack == Decimal("9.7500")
    assert tier.fx_rate_revision == 1
    assert tier.price_per_pack == convert_to_uzs(
        Decimal("9.75"), currency="USD", usd_to_uzs_rate=Decimal("11820.48")
    )

    unconfirmed = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "pack_size": "1",
            "pack_unit_code": "dona",
            "source_price": "50000",
            "source_currency": "UZS",
            "stock_status": "in_stock",
            "active": "true",
        },
        follow_redirects=False,
    )
    assert unconfirmed.status_code == 422
    assert 'value="50000"' in unconfirmed.text

    confirmed = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "pack_size": "1",
            "pack_unit_code": "dona",
            "source_price": "50000",
            "source_currency": "UZS",
            "confirm_currency_change": "true",
            "stock_status": "in_stock",
            "active": "true",
            "tier_id": [str(tier.id)],
            "tier_min_qty": ["10"],
            "tier_source_price": ["45000"],
            "tier_currency": ["UZS"],
            "tier_currency_confirmed": ["true"],
        },
        follow_redirects=False,
    )
    assert confirmed.status_code == 303, confirmed.text
    await test_session.refresh(offer)
    await test_session.refresh(tier)
    assert offer.source_currency == "UZS"
    assert offer.source_price_per_pack == Decimal("50000.0000")
    assert offer.price_per_pack == Decimal("50000.00")
    assert tier.source_currency == "UZS"
    assert tier.source_price_per_pack == Decimal("45000.0000")
    assert tier.price_per_pack == Decimal("45000.00")


@pytest.mark.asyncio
async def test_price_health_keeps_filtered_bulk_deactivation(
    client: TestClient, test_session: AsyncSession
) -> None:
    fixture = await _seed(test_session)
    await _sign_in_admin(client, test_session)
    offer = await test_session.scalar(
        select(ShopProduct).where(ShopProduct.shop_id == fixture.shop_id)
    )
    assert offer is not None
    offer.staleness_state = "stale"
    await test_session.flush()

    page = client.get("/manage/price-health?state=stale")
    assert page.status_code == 200
    assert offer.raw_name in page.text

    response = client.post(
        "/manage/price-health/bulk-deactivate",
        data={"offer_ids": [str(offer.id)]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    await test_session.refresh(offer)
    assert offer.is_active is False
