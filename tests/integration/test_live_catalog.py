"""Open customer pages receive committed catalogue changes without a full reload."""

import re
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct
from app.db.models.shop import ShopProduct
from tests.integration.test_storefront_web import _seed
from tests.integration.test_storefront_web import client as storefront_client


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)


async def test_catalog_fragment_reflects_name_price_and_image_changes(client, test_session):
    fixture = await _seed(test_session)
    url = "/catalog/all?fragment=1"
    first = client.get(url)
    assert first.status_code == 200
    assert "<html" not in first.text and "data-live-root" in first.text
    assert "58 000" in first.text
    old_image = re.search(r"/media/product/\d+\?v=[a-f0-9]+", first.text).group()
    product = await test_session.get(CanonicalProduct, fixture.product_id)
    offer = await test_session.scalar(select(ShopProduct))
    product.name_uz_cyrl = "Янги маҳсулот"
    product.image_url = "/static/store/images/plywood.webp"
    offer.price_per_pack = offer.price_per_base_unit = Decimal("67000")
    await test_session.commit()
    second = client.get(url)
    assert "Янги маҳсулот" in second.text and "67 000" in second.text
    assert old_image not in second.text
    assert second.headers["cache-control"] == "no-store"


async def test_archived_product_updates_open_detail_and_disappears_from_catalog(
    client, test_session
):
    fixture = await _seed(test_session)
    url = f"/product/{fixture.product_id}?fragment=1"
    first = client.get(url)
    assert first.status_code == 200 and 'data-product-active="1"' in first.text
    assert "data-live-preserve" in first.text
    product = await test_session.get(CanonicalProduct, fixture.product_id)
    product.is_active = False
    await test_session.commit()
    updated = client.get(url)
    assert updated.status_code == 200 and 'data-product-active="0"' in updated.text
    assert client.get(f"/product/{fixture.product_id}").status_code == 404
    assert (
        f'data-product-id="{fixture.product_id}"' not in client.get("/catalog/all?fragment=1").text
    )


async def test_admin_image_takes_precedence_over_old_offer_image(client, test_session, monkeypatch):
    fixture = await _seed(test_session)
    product = await test_session.get(CanonicalProduct, fixture.product_id)
    product.image_url = "/static/store/images/plywood.webp"
    await test_session.commit()

    async def old_photo(*args):
        raise AssertionError("The old offer photo must not override the admin photo")

    monkeypatch.setattr(
        "app.db.repositories.shop_repo.ShopRepository.get_photo_for_canonical", old_photo
    )
    response = client.get(f"/media/product/{fixture.product_id}", follow_redirects=False)
    assert response.status_code == 200
    product.is_active = False
    await test_session.commit()
    assert client.get(f"/media/product/{fixture.product_id}").status_code == 404
