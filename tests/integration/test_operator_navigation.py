"""Verified admins can move between their workspace and the customer site."""

from html.parser import HTMLParser

import pytest

from app.core.config import settings
from app.db.models.shop import District
from app.db.models.user import User
from app.web.storefront.session import SESSION_COOKIE, sign_session
from tests.integration.test_visitor_operator import web as _web

web = _web


class Navigation(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.topbar = False
        self.sidebar = False
        self.sidebar_present = False
        self.links: list[dict[str, str | None]] = []
        self.sidebar_links: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "header" and "topbar" in (attributes.get("class") or "").split():
            self.topbar = True
        if tag == "aside" and "admin-sidebar" in (attributes.get("class") or "").split():
            self.sidebar = True
            self.sidebar_present = True
        if tag == "a":
            if self.topbar:
                self.links.append(attributes)
            if self.sidebar:
                self.sidebar_links.append(attributes)

    def handle_endtag(self, tag: str) -> None:
        if tag == "header":
            self.topbar = False
        if tag == "aside":
            self.sidebar = False


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
@pytest.mark.parametrize("role", ["admin", "configured_admin"])
async def test_admin_topbar_opens_customer_site_and_customer_site_returns_to_manage(
    web, test_session, monkeypatch, lang, role
):
    client, _ = web
    test_session.add(District(name_uz="Toshkent", name_ru="Ташкент"))
    user = User(tg_id=991188, role="admin" if role == "admin" else "customer", lang=lang)
    test_session.add(user)
    await test_session.commit()
    if role == "configured_admin":
        monkeypatch.setattr(settings, "admin_tg_ids", [user.tg_id])
    client.cookies.set(SESSION_COOKIE, sign_session(user_id=user.id, tg_id=user.tg_id))
    response = await client.get("/manage")
    assert response.status_code == 200
    navigation = Navigation()
    navigation.feed(response.text)
    links = [link for link in navigation.links if link.get("href") == "/catalog/all"]
    assert len(links) == 1
    assert links[0].get("target") != "_blank"
    storefront = await client.get(links[0]["href"])
    assert storefront.status_code == 200
    navigation = Navigation()
    navigation.feed(storefront.text)
    assert any(link.get("href") == "/manage" for link in navigation.links)


async def test_operator_uses_admin_theme_and_public_chat_keeps_customer_theme(web, test_session):
    client, _ = web
    user = User(tg_id=991189, role="admin")
    test_session.add(user)
    await test_session.commit()
    client.cookies.set(SESSION_COOKIE, sign_session(user_id=user.id, tg_id=user.tg_id))
    inbox = await client.get("/operator")
    assert inbox.status_code == 200
    assert 'class="admin-layout operator-page"' in inbox.text
    assert "/admin.css?v=" in inbox.text
    navigation = Navigation()
    navigation.feed(inbox.text)
    assert navigation.sidebar_present
    assert any(
        link.get("href") == "/operator" and link.get("aria-current") == "page"
        for link in navigation.sidebar_links
    )
    customer_site = [link for link in navigation.links if link.get("href") == "/catalog/all"]
    dashboard = [link for link in navigation.links if link.get("href") == "/manage"]
    assert len(customer_site) == 1 and customer_site[0].get("target") != "_blank"
    assert len(dashboard) == 1
    chat = await client.get("/chat")
    assert chat.status_code == 200
    assert 'class="storefront-b chat-page"' in chat.text
    assert "/storefront.css?v=" in chat.text


async def test_customer_cannot_enter_operator_workspace_or_see_admin_site_switch(web, test_session):
    client, _ = web
    user = User(tg_id=991190, role="customer")
    test_session.add(user)
    await test_session.commit()
    client.cookies.set(SESSION_COOKIE, sign_session(user_id=user.id, tg_id=user.tg_id))
    assert (await client.get("/operator")).status_code == 403
    navigation = Navigation()
    navigation.feed((await client.get("/catalog/all")).text)
    assert not any(link.get("href") == "/manage" for link in navigation.links)
