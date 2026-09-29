"""Admin parity and optional saved-place behaviour through real web routes."""

import base64
from collections.abc import Iterator
from decimal import Decimal
from html import unescape

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Unit
from app.db.models.shop import PriceHistory, ShopProduct
from app.db.models.user import User, UserAddress
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.normalize.text import normalize_query
from app.services.address_service import AddressService, ResolvedLocation
from app.web.storefront.routers.checkout import _resolve_address
from app.web.storefront.schemas import OrderIn
from tests.integration.test_storefront_web import _seed, _sign_in, _sign_in_admin
from tests.integration.test_storefront_web import client as storefront_client


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)


@pytest.mark.asyncio
async def test_admin_catalog_create_duplicate_and_offer_history(
    client: TestClient, test_session: AsyncSession
) -> None:
    fixture = await _seed(test_session)
    _sign_in(client, fixture.user_id)
    assert client.get("/manage").status_code == 403
    assert client.post("/manage/products/new", data={"name": "Untrusted"}).status_code == 403
    assert client.get("/manage/import-template").status_code == 403
    await _sign_in_admin(client, test_session)
    assert client.get("/manage").status_code == 200
    assert client.get("/admin/dashboard").status_code == 200
    template = client.get("/manage/import-template")
    assert template.status_code == 200 and template.content.startswith(b"PK")

    fields = {
        "name": "Test panel 12 mm",
        "category_id": str(fixture.category_id),
        "unit_code": "dona",
        "size": "2500x1200",
        "thickness": "12",
        "name_ru": "Тестовая плита 12 мм",
        "name_uz_cyrl": "Тест плита 12 мм",
    }
    created = client.post("/manage/products/new", data=fields, follow_redirects=False)
    assert created.status_code == 303, created.text
    product_id = int(created.headers["location"].split("/")[-1])
    product = await test_session.get(CanonicalProduct, product_id)
    assert product is not None and product.source == "admin"
    assert product.attributes["stock_unverified"]
    results = await CatalogRepository(test_session).search_canonical_products(
        normalize_query(fields["name_ru"]).text_norm, require_offers=False
    )
    assert product.id in [row.id for row in results]
    assert client.post("/manage/products/new", data=fields).status_code == 409
    assert (
        client.post(
            "/manage/products/new",
            data={**fields, "csrf_token": client.headers["X-CSRF-Token"]},
            headers={"X-CSRF-Token": ""},
        ).status_code
        == 409
    )
    assert (
        client.post("/manage/products/new", data={**fields, "force_new": "true"}).status_code == 409
    )
    assert client.get(f"/manage/products/{product_id}").status_code == 200
    different_variant = {**fields, "thickness": "14"}
    assert client.post("/manage/products/new", data=different_variant).status_code == 409
    second = client.post(
        "/manage/products/new",
        data={**different_variant, "force_new": "true", "price": "50000", "stock_status": "out"},
        follow_redirects=False,
    )
    assert second.status_code == 303
    second_id = int(second.headers["location"].split("/")[-1])
    assert (
        client.post(
            f"/manage/products/{second_id}",
            data={**fields, "active": "true"},
        ).status_code
        == 409
    )
    assert (
        await test_session.scalar(
            select(ShopProduct.id).where(ShopProduct.canonical_id == second_id)
        )
        is not None
    )
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9GkZ4AAAAASUVORK5CYII="
    )
    edited = client.post(
        f"/manage/products/{product_id}",
        data={**fields, "active": "true"},
        files={"photo": ("product.png", tiny_png, "image/png")},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    await test_session.refresh(product)
    assert product.image_url and client.get(product.image_url).content == tiny_png

    offer_fields = {
        "pack_size": "1",
        "pack_unit_code": "dona",
        "price": "52000",
        "stock_status": "out",
        "stock_qty": "0",
    }
    response = client.post(
        f"/manage/products/{product_id}/offers", data=offer_fields, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    invalid_offer = client.post(
        f"/manage/products/{product_id}/offers",
        data={
            "pack_size": "-1",
            "pack_unit_code": "dona",
            "price": "0",
            "stock_status": "low",
            "description": "Keep this input",
        },
        follow_redirects=False,
    )
    assert invalid_offer.status_code == 422
    assert 'value="-1"' in invalid_offer.text and "Keep this input" in invalid_offer.text
    oversized_price = client.post(
        f"/manage/products/{product_id}/offers",
        data={
            "pack_size": "1",
            "pack_unit_code": "dona",
            "price": "9999999999999.99",
            "stock_status": "low",
            "description": "Preserve oversized price",
        },
        follow_redirects=False,
    )
    assert oversized_price.status_code == 422
    assert 'value="9999999999999.99"' in oversized_price.text
    assert any(
        message in unescape(oversized_price.text)
        for message in (
            "Ma'lumotlarni tekshiring.",
            "Маълумотларни текширинг.",
            "Проверьте данные.",
        )
    )
    too_long_price = "9" * 65
    long_number_response = client.post(
        f"/manage/products/{product_id}/offers",
        data={
            "pack_size": "1",
            "pack_unit_code": "dona",
            "price": too_long_price,
            "stock_status": "low",
            "description": "Preserve long number",
        },
        follow_redirects=False,
    )
    assert long_number_response.status_code == 422
    assert f'value="{too_long_price}"' in long_number_response.text
    offer = await test_session.scalar(
        select(ShopProduct).where(ShopProduct.canonical_id == product_id)
    )
    assert offer is not None and offer.price_per_pack == Decimal("52000")
    invalid_edit = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "pack_size": "3",
            "pack_unit_code": "missing-unit",
            "price": "53000",
            "stock_status": "low",
            "description": "Keep edit input",
            "active": "true",
        },
        follow_redirects=False,
    )
    assert invalid_edit.status_code == 422
    assert 'value="3"' in invalid_edit.text and "Keep edit input" in invalid_edit.text
    oversized_pack = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "pack_size": "1e9999",
            "pack_unit_code": "dona",
            "price": "53000",
            "stock_status": "low",
            "description": "Preserve oversized pack",
            "active": "true",
        },
        follow_redirects=False,
    )
    assert oversized_pack.status_code == 422
    assert 'value="1e9999"' in oversized_pack.text
    long_description = "x" * (settings.listing_max_description_len + 1)
    long_description_response = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "pack_size": "1",
            "pack_unit_code": "dona",
            "price": "53000",
            "stock_status": "low",
            "description": long_description,
            "active": "true",
        },
        follow_redirects=False,
    )
    assert long_description_response.status_code == 422
    assert long_description in long_description_response.text
    assert (
        await test_session.scalar(
            select(func.count())
            .select_from(PriceHistory)
            .where(PriceHistory.shop_product_id == offer.id)
        )
        == 1
    )
    assert (
        client.post(
            f"/manage/offers/{offer.id}",
            data={"price": "53000", "stock_status": "in_stock", "stock_qty": "5", "active": "true"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    await test_session.refresh(offer)
    assert offer.price_per_pack == Decimal("53000") and offer.stock_qty is None
    assert (
        await test_session.scalar(
            select(func.count())
            .select_from(PriceHistory)
            .where(PriceHistory.shop_product_id == offer.id)
        )
        == 2
    )
    assert (
        client.post(
            f"/manage/products/{product_id}/offers",
            data={**offer_fields, "price": "53000", "stock_status": "low"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        await test_session.scalar(
            select(func.count())
            .select_from(PriceHistory)
            .where(PriceHistory.shop_product_id == offer.id)
        )
        == 2
    )
    changed_pack = client.post(
        f"/manage/offers/{offer.id}",
        data={
            "price": "53000",
            "stock_status": "low",
            "active": "true",
            "pack_size": "2",
            "pack_unit_code": "dona",
            "description": "Two piece pack",
        },
        follow_redirects=False,
    )
    assert changed_pack.status_code == 303
    await test_session.refresh(offer)
    assert offer.pack_size == Decimal("2")
    assert offer.description == "Two piece pack"
    assert offer.stock_qty is None
    assert offer.price_per_base_unit == Decimal("26500.0000")
    assert (
        await test_session.scalar(
            select(func.count())
            .select_from(PriceHistory)
            .where(PriceHistory.shop_product_id == offer.id)
        )
        == 3
    )
    assert (
        client.post(f"/manage/products/{product_id}/archive", follow_redirects=False).status_code
        == 303
    )
    await test_session.refresh(product)
    await test_session.refresh(offer)
    assert product.is_active is False and offer.is_active is True
    assert await ShopRepository(test_session).get_active_offers_for_canonicals([product_id]) == []
    assert (
        client.post(f"/manage/products/{product_id}/restore", follow_redirects=False).status_code
        == 303
    )
    await test_session.refresh(product)
    await test_session.refresh(offer)
    assert product.is_active is True and offer.is_active is True
    assert await ShopRepository(test_session).get_active_offers_for_canonicals([product_id])
    test_session.add(Unit(code="kg", name_uz="kg", name_ru="кг", dimension="mass"))
    await test_session.flush()
    assert (
        client.post(
            f"/manage/products/{product_id}",
            data={**fields, "unit_code": "kg", "active": "true"},
        ).status_code
        == 409
    )
    previous_slug = product.slug
    assert (
        client.post(
            f"/manage/products/{product_id}",
            data={**fields, "name": "Renamed test panel", "active": "true"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    await test_session.refresh(product)
    assert product.slug != previous_slug
    assert (
        client.post(
            "/manage/products/new",
            data={**fields, "force_new": "true"},
            follow_redirects=False,
        ).status_code
        == 303
    )


@pytest.mark.asyncio
async def test_only_super_admin_promotes_existing_telegram_account(
    client: TestClient, test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = await _seed(test_session)
    admin = await _sign_in_admin(client, test_session)
    assert client.get("/manage/admins").status_code == 403
    assert client.post("/manage/admins", data={"tg_id": str(fixture.user_id)}).status_code == 403
    monkeypatch.setattr(settings, "super_admin_tg_ids", [admin.tg_id])
    assert client.get("/manage/admins").status_code == 200
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/manage/admins", data={"tg_id": "5550001"}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/manage/admins", data={"tg_id": "999999999"}).status_code == 422
    assert (
        client.post("/manage/admins", data={"tg_id": "5550001"}, follow_redirects=False).status_code
        == 303
    )


@pytest.mark.asyncio
async def test_text_only_saved_place_uses_district_and_no_fabricated_pin(
    client: TestClient, test_session: AsyncSession
) -> None:
    fixture = await _seed(test_session)
    _sign_in(client, fixture.user_id)
    response = client.post(
        "/account/addresses",
        data={"address_text": "Chilonzor 12-uy", "district_id": str(1)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    saved = await test_session.scalar(
        select(UserAddress).where(UserAddress.user_id == fixture.user_id)
    )
    assert saved is not None and saved.lat is None and saved.lng is None
    assert saved.district_id == 1


@pytest.mark.asyncio
async def test_outside_pin_requires_a_selected_district_before_saving(
    client: TestClient, test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = await _seed(test_session)
    _sign_in(client, fixture.user_id)
    user = await test_session.get(User, fixture.user_id)
    assert user is not None
    user.district_id = None
    await test_session.flush()

    async def outside(self: AddressService, lat: float, lng: float, lang: str) -> ResolvedLocation:
        return ResolvedLocation(
            lat=Decimal(str(lat)),
            lng=Decimal(str(lng)),
            address_text=None,
            district_id=None,
        )

    monkeypatch.setattr(AddressService, "resolve", outside)
    body = {"address_text": "STAGING address 12", "lat": "41.25", "lng": "69.2"}
    denied = client.post("/account/addresses", data=body, follow_redirects=False)
    assert denied.headers["location"] == "/account?msg=manage_district_required"
    assert await test_session.scalar(select(UserAddress.id)) is None
    accepted = client.post(
        "/account/addresses", data={**body, "district_id": "1"}, follow_redirects=False
    )
    assert accepted.status_code == 303
    saved = await test_session.scalar(select(UserAddress))
    assert saved is not None and saved.district_id == 1
    assert saved.lat == Decimal("41.25")

    another = await _resolve_address(
        test_session,
        user,
        OrderIn(address_text="Other location 12", district_id=1, lat=41.25, lng=69.2),
        lang="uz_latn",
    )
    assert another is not None and another[1] == 1 and another[2] is not None
