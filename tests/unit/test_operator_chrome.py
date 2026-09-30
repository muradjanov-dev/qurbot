"""Operator chrome gives staff an explicit return path and fresh stylesheet URLs."""

import importlib.util
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.web.storefront import deps
from tests.unit.test_chat_frontend import template_env


class HeaderLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.header = False
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "header" and "topbar" in attrs.get("class", "").split():
            self.header = True
        if tag == "a" and self.header:
            self.current = {"href": attrs.get("href"), "text": ""}

    def handle_data(self, text):
        if self.current is not None:
            self.current["text"] += text

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None
        if tag == "header":
            self.header = False


def render_chrome(active, lang):
    html = (
        template_env()
        .get_template("base.html")
        .render(
            lang=lang,
            admin_surface=True,
            admin_active=active,
            is_admin=True,
            user=SimpleNamespace(id=1, tg_id=1, full_name="Admin", username=None),
            path="/operator" if active == "chats" else "/manage",
            static_url="/static/store",
            js_messages={},
            request=None,
        )
    )
    parser = HeaderLinks()
    parser.feed(html)
    return parser.links


@pytest.mark.parametrize(
    ("lang", "label"),
    [
        ("uz_latn", "Boshqaruvga qaytish"),
        ("uz_cyrl", "Бошқарувга қайтиш"),
        ("ru", "Вернуться к управлению"),
    ],
)
def test_operator_return_link_explains_its_destination(lang, label):
    links = render_chrome("chats", lang)
    assert any(link["href"] == "/manage" and label in link["text"] for link in links)


def test_regular_dashboard_keeps_tezqur_brand_breadcrumb():
    links = render_chrome("dashboard", "uz_latn")
    assert any(link["href"] == "/manage" and link["text"] == "Tezqur" for link in links)


def test_operator_css_only_change_invalidates_shared_asset_version(tmp_path):
    source = tmp_path / "deps.py"
    source.write_bytes(Path(deps.__file__).read_bytes())
    static = tmp_path / "static"
    static.mkdir()
    stylesheet = static / "operator.css"

    def version():
        spec = importlib.util.spec_from_file_location("operator_asset_probe", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ASSET_VERSION

    stylesheet.write_text(".operator-shell { background: white; }")
    before = version()
    stylesheet.write_text(".operator-shell { background: #f4f7f5; }")
    assert version() != before
