"""End-to-end tests for the customer website (app/web/storefront).

Exercised the way a browser drives it: HTML pages, then the JSON endpoints the
basket and checkout call. The order test is the important one -- it is the only
path on the site that spends the customer's money, and it must refuse a price
the client made up.
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
from app.db.models.ops import PebbleAward
from app.db.models.order import Order, OrderItem, OrderShopPart
from app.db.models.shop import District, Shop, ShopDeliveryRule, ShopProduct
from app.db.models.user import User, UserAddress
from app.db.session import get_db_session
from app.main import app
from app.web.storefront.session import SESSION_COOKIE, sign_session


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield test_session

    async def _no_notifications(*args: object, **kwargs: object) -> None:
        return None

    # The site is being tested, not Telegram delivery: the notification path
    # has its own coverage and would otherwise reach the network.
    monkeypatch.setattr("app.web.storefront.routers.checkout.notify_order", _no_notifications)
    # Every fixture below matches by approved alias (Stage 1), so the LLM
    # fallback should never fire; disabling it makes that a guarantee.
    monkeypatch.setattr(settings, "llm_enabled", False)
    # `enabled_category_slugs` is a launch-scope business decision that changes
    # with the catalogue. These tests are about the website, so they run against
    # an unrestricted catalogue rather than tracking whatever is switched on.
    monkeypatch.setattr(settings, "enabled_category_slugs", [])

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db_session, None)


class Fixtures:
    """Ids of the seeded rows, so tests read as behaviour rather than setup."""

    def __init__(self, category_id: int, product_id: int, shop_id: int, user_id: int) -> None:
        self.category_id = category_id
        self.product_id = product_id
        self.shop_id = shop_id
        self.user_id = user_id


CUSTOMER_TG_ID = 5550001


async def _seed(session: AsyncSession) -> Fixtures:
    session.add(Unit(code="dona", name_uz="Dona", name_ru="Штука", dimension="count"))
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    category = Category(slug="gipsokarton", name_uz="Gipsokarton", name_ru="Гипсокартон")
    session.add_all([district, category])
    await session.flush()

    product = CanonicalProduct(
        slug="gipsokarton-12-5",
        name_uz="Gipsokarton 12.5mm",
        name_uz_cyrl="Гипсокартон 12.5мм",
        name_ru="Гипсокартон 12.5мм",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="gipsokarton 12.5mm gipsokarton",
        reference_price=Decimal("62000.00"),
    )
    session.add(product)
    await session.flush()

    session.add(
        ProductAlias(
            canonical_id=product.id,
            alias_norm="gipsokarton",
            alias_raw="gipsokarton",
            source="seed",
            confidence=Decimal("1.00"),
            is_approved=True,
        )
    )

    shop = Shop(
        name="Baraka Qurilish",
        phone="+998901112233",
        district_id=district.id,
        address="Chilonzor 7",
        owner_tg_id=7770001,
    )
    session.add(shop)
    await session.flush()

    session.add_all(
        [
            ShopProduct(
                shop_id=shop.id,
                canonical_id=product.id,
                raw_name="Gipsokarton 12.5",
                raw_unit="dona",
                pack_size=Decimal("1"),
                pack_unit_code="dona",
                price_per_pack=Decimal("58000.00"),
                price_per_base_unit=Decimal("58000.0000"),
                stock_status="in_stock",
                staleness_state="fresh",
            ),
            ShopDeliveryRule(
                shop_id=shop.id,
                district_id=district.id,
                fee=Decimal("40000.00"),
                free_above=Decimal("1000000.00"),
                min_order=Decimal("0.00"),
                eta_hours=24,
            ),
        ]
    )

    # Given a district, because that is what an onboarded customer has -- and
    # delivery rules resolve per district.
    user = User(
        tg_id=CUSTOMER_TG_ID,
        full_name="Test Mijoz",
        lang="uz_latn",
        district_id=district.id,
    )
    session.add(user)
    await session.flush()
    await session.commit()

    return Fixtures(category.id, product.id, shop.id, user.id)


def _sign_in(client: TestClient, user_id: int, tg_id: int = CUSTOMER_TG_ID) -> None:
    client.cookies.set(SESSION_COOKIE, sign_session(user_id=user_id, tg_id=tg_id))


def _basket_line(product_id: int, qty: str = "10") -> dict[str, object]:
    return {"line_no": 1, "canonical_id": product_id, "qty": qty, "unit_code": "dona"}


# ── pages ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_home_page_renders(client: TestClient, test_session: AsyncSession) -> None:
    await _seed(test_session)
    response = client.get("/")
    assert response.status_code == 200
    assert "QurBot" in response.text
    assert "Gipsokarton" in response.text  # the section tile


@pytest.mark.asyncio
async def test_catalog_and_product_pages(client: TestClient, test_session: AsyncSession) -> None:
    data = await _seed(test_session)

    listing = client.get(f"/catalog/{data.category_id}")
    assert listing.status_code == 200
    assert "Gipsokarton 12.5mm" in listing.text

    detail = client.get(f"/product/{data.product_id}")
    assert detail.status_code == 200
    assert "58 000" in detail.text  # cheapest live offer, space-grouped

    assert client.get("/product/999999").status_code == 404


@pytest.mark.asyncio
async def test_language_switch_sets_cookie(client: TestClient, test_session: AsyncSession) -> None:
    await _seed(test_session)
    response = client.get("/lang/ru?next=/catalog", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/catalog"
    assert client.cookies.get("qb_lang") == "ru"

    assert "Каталог" in client.get("/catalog").text


@pytest.mark.asyncio
async def test_language_switch_refuses_offsite_redirect(
    client: TestClient, test_session: AsyncSession
) -> None:
    await _seed(test_session)
    response = client.get("/lang/ru?next=https://evil.example", follow_redirects=False)
    assert response.headers["location"] == "/"


@pytest.mark.asyncio
async def test_orders_page_requires_login(client: TestClient, test_session: AsyncSession) -> None:
    await _seed(test_session)
    response = client.get("/orders", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


# ── basket & quote ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_matches_an_approved_alias(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    response = client.post("/api/basket/parse", json={"text": "10 dona gipsokarton"})
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    line = body["lines"][0]
    assert line["status"] == "ok"
    assert line["canonical_id"] == data.product_id
    assert Decimal(line["qty"]) == Decimal("10")


@pytest.mark.asyncio
async def test_parse_rejects_empty_text(client: TestClient, test_session: AsyncSession) -> None:
    await _seed(test_session)
    body = client.post("/api/basket/parse", json={"text": "   "}).json()
    assert body["ok"] is False
    assert body["error"]


@pytest.mark.asyncio
async def test_quote_prices_the_basket(client: TestClient, test_session: AsyncSession) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)
    body = client.post("/api/quote", json={"lines": [_basket_line(data.product_id)]}).json()

    assert body["ok"] is True
    variant = body["variants"][0]
    assert variant["items"][0]["name"] == "Gipsokarton 12.5mm"
    # 10 × 58 000 = 580 000 items, plus the district's 40 000 delivery fee.
    assert Decimal(variant["grand_total_raw"]) == Decimal("620000")


@pytest.mark.asyncio
async def test_quote_ignores_products_outside_the_catalogue(
    client: TestClient, test_session: AsyncSession
) -> None:
    await _seed(test_session)
    body = client.post("/api/quote", json={"lines": [_basket_line(999999)]}).json()
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_quote_refuses_an_unorderable_quantity(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    body = client.post(
        "/api/quote", json={"lines": [_basket_line(data.product_id, qty="-5")]}
    ).json()
    assert body["ok"] is False


# ── ordering ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_order_requires_a_signed_in_customer(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    response = client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "+998901234567",
            "address_text": "Chilonzor 7",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_order_creates_the_full_row_set_and_awards_pebbles(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)

    body = client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "90 123 45 67",
            "address_text": "Chilonzor 7-kvartal, 12-uy",
            "comment": "2-qavat",
        },
    ).json()
    assert body["ok"] is True, body

    order = (await test_session.execute(select(Order))).scalars().one()
    assert order.id == body["order_id"]
    assert order.grand_total_quoted == Decimal("620000")
    # The typed number is stored in one canonical form, as the shop will dial it.
    assert order.contact_phone == "+998901234567"
    assert order.comment == "2-qavat"

    parts = (await test_session.execute(select(OrderShopPart))).scalars().all()
    assert [part.shop_id for part in parts] == [data.shop_id]
    items = (await test_session.execute(select(OrderItem))).scalars().all()
    assert len(items) == 1
    assert items[0].line_total == Decimal("580000")

    awards = (await test_session.execute(select(PebbleAward))).scalars().all()
    assert len(awards) == 1
    assert awards[0].amount == body["pebbles"] > 0

    # The quote snapshot is kept, so the order can always be read back at the
    # price it was placed at.
    assert Decimal(order.quote.payload["grand_total_uzs"]) == Decimal("620000")
    assert order.quote.payload["shop_groups"][0]["shop_id"] == data.shop_id


@pytest.mark.asyncio
async def test_order_refuses_a_total_the_client_made_up(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)

    body = client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "+998901234567",
            "address_text": "Chilonzor 7",
            "expected_total": "1",
        },
    ).json()

    assert body["ok"] is False
    assert body["price_changed"] is True
    assert Decimal(body["variant"]["grand_total_raw"]) == Decimal("620000")
    assert (await test_session.execute(select(Order))).scalars().first() is None


@pytest.mark.asyncio
async def test_order_refuses_a_bad_phone_number(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)

    body = client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "12345",
            "address_text": "Chilonzor 7",
        },
    ).json()
    assert body["ok"] is False
    assert (await test_session.execute(select(Order))).scalars().first() is None


@pytest.mark.asyncio
async def test_order_refuses_another_customers_saved_address(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)

    stranger = User(tg_id=999333, full_name="Boshqa", lang="uz_latn")
    test_session.add(stranger)
    await test_session.flush()
    address = UserAddress(
        user_id=stranger.id,
        lat=Decimal("41.2995"),
        lng=Decimal("69.2401"),
        address_text="Yunusobod 4",
        is_default=True,
    )
    test_session.add(address)
    await test_session.commit()

    _sign_in(client, data.user_id)
    body = client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "+998901234567",
            "address_id": address.id,
        },
    ).json()

    assert body["ok"] is False
    assert (await test_session.execute(select(Order))).scalars().first() is None


# ── shop portal ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shop_panel_is_invisible_to_non_owners(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)
    assert client.get(f"/shop/{data.shop_id}").status_code == 404


@pytest.mark.asyncio
async def test_shop_owner_can_update_a_price(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    owner = User(tg_id=7770001, full_name="Do'kon egasi", role="shop_owner", lang="uz_latn")
    test_session.add(owner)
    await test_session.flush()
    await test_session.commit()
    _sign_in(client, owner.id, tg_id=7770001)

    offer = (await test_session.execute(select(ShopProduct))).scalars().one()
    response = client.post(
        f"/shop/{data.shop_id}/products/{offer.id}",
        data={"price": "61000", "stock_status": "low", "page": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    await test_session.refresh(offer)
    assert offer.price_per_pack == Decimal("61000")
    assert offer.stock_status == "low"


async def _sign_in_owner(client: TestClient, session: AsyncSession) -> User:
    owner = User(tg_id=7770001, full_name="Do'kon egasi", role="shop_owner", lang="uz_latn")
    session.add(owner)
    await session.flush()
    await session.commit()
    _sign_in(client, owner.id, tg_id=7770001)
    return owner


@pytest.mark.asyncio
async def test_every_shop_page_renders_for_its_owner(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    await _sign_in_owner(client, test_session)

    for path in ("", "/products", "/orders", "/delivery", "/import"):
        response = client.get(f"/shop/{data.shop_id}{path}")
        assert response.status_code == 200, path
        assert "Baraka Qurilish" in response.text


@pytest.mark.asyncio
async def test_owner_can_save_a_delivery_rule(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    await _sign_in_owner(client, test_session)

    response = client.post(
        f"/shop/{data.shop_id}/delivery",
        data={
            "district_id": "",
            "fee": "25 000",
            "free_above": "500000",
            "min_order": "0",
            "eta_hours": "12",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    rules = (await test_session.execute(select(ShopDeliveryRule))).scalars().all()
    # The district-wide rule the fixture seeded, plus the new all-districts one.
    added = [rule for rule in rules if rule.district_id is None]
    assert len(added) == 1
    assert added[0].fee == Decimal("25000")
    assert added[0].eta_hours == 12


@pytest.mark.asyncio
async def test_owner_answers_an_order_and_the_customer_sees_it(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)
    placed = client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "+998901234567",
            "address_text": "Chilonzor 7",
        },
    ).json()
    assert placed["ok"] is True

    # The customer's own page renders the order they just placed.
    detail = client.get(f"/orders/{placed['order_id']}")
    assert detail.status_code == 200
    assert "Gipsokarton 12.5mm" in detail.text
    assert client.get("/orders").status_code == 200

    await _sign_in_owner(client, test_session)
    part = (await test_session.execute(select(OrderShopPart))).scalars().one()
    response = client.post(f"/shop/{data.shop_id}/orders/{part.id}/accept", follow_redirects=False)
    assert response.status_code == 303

    await test_session.refresh(part)
    assert part.shop_response == "accepted"
    assert part.status == "accepted"
    assert part.responded_at is not None


@pytest.mark.asyncio
async def test_owner_cannot_answer_another_shops_order(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)
    client.post(
        "/api/order",
        json={
            "lines": [_basket_line(data.product_id)],
            "phone": "+998901234567",
            "address_text": "Chilonzor 7",
        },
    )

    other = Shop(
        name="Boshqa do'kon",
        phone="+998907654321",
        district_id=1,
        address="Yunusobod 1",
        owner_tg_id=8880002,
    )
    test_session.add(other)
    await test_session.flush()
    stranger = User(tg_id=8880002, full_name="Begona", role="shop_owner", lang="uz_latn")
    test_session.add(stranger)
    await test_session.flush()
    await test_session.commit()
    _sign_in(client, stranger.id, tg_id=8880002)

    part = (await test_session.execute(select(OrderShopPart))).scalars().one()
    assert client.post(f"/shop/{other.id}/orders/{part.id}/accept").status_code == 404

    await test_session.refresh(part)
    assert part.shop_response == "pending"


@pytest.mark.asyncio
async def test_customer_pages_render(client: TestClient, test_session: AsyncSession) -> None:
    data = await _seed(test_session)

    assert client.get("/basket").status_code == 200
    assert client.get("/login").status_code == 200

    _sign_in(client, data.user_id)
    assert client.get("/checkout?strategy=CHEAPEST_TOTAL").status_code == 200
    assert client.get("/account").status_code == 200


@pytest.mark.asyncio
async def test_customer_can_save_and_default_an_address(
    client: TestClient, test_session: AsyncSession
) -> None:
    data = await _seed(test_session)
    _sign_in(client, data.user_id)

    response = client.post(
        "/account/addresses",
        data={
            "address_text": "Chilonzor 7-kvartal, 12-uy",
            "lat": "41.2750",
            "lng": "69.2030",
            "label": "Obyekt",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    saved = (await test_session.execute(select(UserAddress))).scalars().one()
    assert saved.address_text == "Chilonzor 7-kvartal, 12-uy"
    assert saved.label == "Obyekt"
    assert saved.is_default is True

    deleted = client.post(f"/account/addresses/{saved.id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert (await test_session.execute(select(UserAddress))).scalars().first() is None
