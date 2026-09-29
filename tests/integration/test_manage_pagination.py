"""All-category filters must survive paging without an integer parsing error."""

import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct
from tests.integration.test_storefront_web import (
    _seed,
    _sign_in,
    _sign_in_admin,
)
from tests.integration.test_storefront_web import (
    client as storefront_client,
)

client = storefront_client


@pytest.mark.asyncio
async def test_blank_category_pagination_and_status_links_keep_filters(
    client, test_session, monkeypatch
):
    fixture = await _seed(test_session)
    test_session.add(
        CanonicalProduct(
            slug="paging-second",
            name_uz="Gipsokarton 15mm",
            name_ru="Гипсокартон 15мм",
            name_uz_cyrl="Гипсокартон 15мм",
            category_id=fixture.category_id,
            base_unit_code="dona",
            search_doc="gipsokarton 15mm",
        )
    )
    await test_session.flush()
    monkeypatch.setattr(settings, "web_manage_products_page_size", 1)
    await _sign_in_admin(client, test_session)
    reported = client.get("/manage/products?page=2&q=&category_id=&status=all")
    assert reported.status_code == 200, reported.text
    assert "Gipsokarton 15mm" in reported.text
    page = client.get(
        "/manage/products", params={"q": "Gipsokarton", "category_id": "", "status": "all"}
    )
    assert page.status_code == 200
    links = [unescape(url) for url in re.findall(r'href="(/manage/products\?[^\"]+)"', page.text)]
    assert links
    for link in links:
        query = parse_qs(urlsplit(link).query, keep_blank_values=True)
        assert "category_id" not in query
        assert query["q"] == ["Gipsokarton"]
    next_link = next(link for link in links if parse_qs(urlsplit(link).query).get("page") == ["2"])
    second = client.get(next_link)
    assert second.status_code == 200 and "Gipsokarton 15mm" in second.text
    numeric = client.get("/manage/products", params={"category_id": str(fixture.category_id)})
    assert numeric.status_code == 200
    assert f'value="{fixture.category_id}" selected' in numeric.text
    assert client.get("/manage/products?category_id=not-a-number").status_code == 422
    _sign_in(client, fixture.user_id)
    assert client.get("/manage/products?page=2&category_id=").status_code == 403
