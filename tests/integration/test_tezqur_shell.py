"""Role-aware production entry points keep guest sign-in discoverable."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_storefront_web import _seed, _sign_in, _sign_in_admin
from tests.integration.test_storefront_web import client as storefront_client


@pytest.fixture
def client(test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from storefront_client.__wrapped__(test_session, monkeypatch)


async def test_guest_has_explicit_telegram_login_and_five_customer_tabs(client, test_session):
    await _seed(test_session)
    page = client.get("/catalog/all")
    assert page.status_code == 200
    assert "data-telegram-login" in page.text
    assert "Tezqur" in page.text
    assert 'name="color-scheme" content="light"' in page.text
    assert "prototype/" not in page.text
    assert "admin-sidebar" not in page.text
    tabs = page.text.split('<nav class="tabbar"', 1)[1].split("</nav>", 1)[0]
    assert tabs.count("<a ") == 5


async def test_signed_in_admin_has_one_product_navigation_entry(client, test_session):
    await _seed(test_session)
    await _sign_in_admin(client, test_session)
    page = client.get("/manage")
    assert page.status_code == 200
    sidebar = page.text.split('<nav class="admin-nav">', 1)[1].split("</nav>", 1)[0]
    assert sidebar.count('href="/manage/products"') == 1
    assert sidebar.count("<a ") == 6
    assert "admin.css" in page.text
    assert "prototype/" not in page.text


async def test_customer_cannot_gain_admin_access_from_manage_query_parameters(client, test_session):
    fixture = await _seed(test_session)
    _sign_in(client, fixture.user_id)
    page = client.get("/manage?variant=A")
    assert page.status_code == 403
    assert "prototype-view" not in page.text
