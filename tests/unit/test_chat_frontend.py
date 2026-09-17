"""Template accessibility/localization and unconfirmed product presentation."""

import json
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.web.storefront.routers.catalog import _needs_confirmation

TEMPLATES = Path(__file__).parents[2] / "app/web/storefront/templates"


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.labels: list[str] = []
        self.logs: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if value := values.get("id"):
            self.ids.append(value)
        if tag == "label" and (value := values.get("for")):
            self.labels.append(value)
        if values.get("role") == "log":
            self.logs.append(values)


def template_env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True)
    env.globals.update(t=t, csrf_token=lambda request: "test-csrf")
    return env


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
@pytest.mark.parametrize("authenticated", [True, False])
def test_chat_template_accessibility_and_localization(lang: str, authenticated: bool) -> None:
    html = (
        template_env()
        .get_template("chat.html")
        .render(
            lang=lang,
            user=object() if authenticated else None,
            path="/chat",
            static_url="/static/store",
            js_messages={},
            request=None,
        )
    )
    audit = PageAudit()
    audit.feed(html)
    assert len(audit.ids) == len(set(audit.ids))
    assert all(label in audit.ids for label in audit.labels)
    assert "web_chat_" not in html
    assert 'name="csrf-token" content="test-csrf"' in html
    if authenticated:
        assert audit.logs[0]["aria-label"] == t("web_chat_history", lang=lang)
        assert audit.logs[0]["aria-live"] == "polite"
        raw = html.split('<script id="chat-strings" type="application/json">')[1]
        assert json.loads(raw.split("</script>")[0])["retry"] == t("web_chat_retry", lang=lang)
    else:
        assert 'href="/login?next=/chat"' in html
        assert "chat.js" not in html


@pytest.mark.parametrize(
    ("attributes", "price", "expected"),
    [
        ({}, None, True),
        ({}, Decimal("10"), False),
        ({"price_on_request": True}, Decimal("10"), True),
        ({"stock_unverified": True}, Decimal("10"), True),
    ],
)
def test_unconfirmed_product_has_no_add_control(
    attributes: dict[str, bool],
    price: Decimal | None,
    expected: bool,
) -> None:
    product = CanonicalProduct(
        id=1,
        category_id=1,
        attributes=attributes,
        base_unit_code="dona",
    )
    confirmation = _needs_confirmation(product, price)
    assert confirmation is expected
    html = (
        template_env()
        .get_template("product.html")
        .render(
            lang="ru",
            user=None,
            path="/product/1",
            static_url="/static/store",
            js_messages={},
            request=None,
            product=product,
            product_name="<script>bad</script>",
            price_label="",
            needs_confirmation=confirmation,
        )
    )
    assert ("data-add-product" not in html) is expected
    assert (t("web_product_confirm_hint", lang="ru") in html) is expected
    assert "<script>bad</script>" not in html
