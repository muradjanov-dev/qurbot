"""Adapt isolated seed data to three visual prototypes on existing page routes."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlencode

from fastapi import Request

from app.core.i18n import t
from app.web.storefront.prototypes.strings import LABELS

SCREENS = {
    "dashboard": "/manage",
    "products": "/manage/products",
    "catalog": "/catalog/all",
    "chat": "/chat",
    "cart": "/basket",
}
TEMPLATES = {
    "manage.html": "dashboard",
    "manage_products.html": "products",
    "manage_product_form.html": "products",
    "products.html": "catalog",
    "catalog.html": "catalog",
    "home.html": "catalog",
    "chat.html": "chat",
    "basket.html": "cart",
}
LANGS = ("uz_latn", "uz_cyrl", "ru")


def money(value: Decimal, *, currency: str, lang: str, fixed: bool = False) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, fraction = f"{rounded:.2f}".split(".")
    grouped = f"{int(whole):,}".replace(",", " ")
    if fixed or fraction != "00":
        grouped += "," + fraction
    suffix = (
        "USD" if currency == "USD" else {"uz_latn": "so‘m", "uz_cyrl": "сўм", "ru": "сум"}[lang]
    )
    return f"{grouped} {suffix}"


def preview_context(
    request: Request, template: str, lang: str
) -> tuple[str, dict[str, Any]] | None:
    if template not in TEMPLATES:
        return None
    variant = request.query_params.get("variant", "A").upper()
    if variant not in {"A", "B", "C"}:
        variant = "A"
    chosen = request.query_params.get("lang", lang)
    lang = chosen if chosen in LANGS else "uz_cyrl"
    index = LANGS.index(lang)
    labels = {key: values[index] for key, values in LABELS.items()}
    labels["chat"] = labels["ai"]
    labels["delivery_notice"] = t("sales_delivery_notice", lang=lang)
    screen = TEMPLATES[template]
    rate = request.app.state.design_rate
    products = []
    for original in request.app.state.design_products:
        product = dict(original)
        source_amount = Decimal(product["source_price"])
        amount = source_amount * rate if product["source_currency"] == "USD" else source_amount
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        dollars = source_amount if product["source_currency"] == "USD" else amount / rate
        product.update(
            name=product["names"][lang],
            category=product["categories"][lang],
            description=product["names"][lang],
            price_uzs=str(amount),
            price_usd=f"{dollars:.2f}",
            uzs=money(amount, currency="UZS", lang=lang),
            usd=("≈ " if product["source_currency"] == "UZS" else "")
            + money(dollars, currency="USD", lang=lang, fixed=True),
        )
        unit = {
            "dona": ("dona", "дона", "шт."),
            "kg": ("kg", "кг", "кг"),
            "m3": ("m³", "м³", "м³"),
        }.get(product["unit"], (product["unit"],) * 3)[index]
        product["pack_label"] = f"{product['pack_size']} {unit}"
        products.append(product)

    def screen_url(target: str) -> str:
        target = {"ai": "chat", "chats": "chat"}.get(target, target)
        if target not in SCREENS:
            return "#" + target
        return SCREENS[target] + "?" + urlencode({"variant": variant, "lang": lang})

    data = {
        "screen": screen,
        "variant": variant,
        "lang": lang,
        "L": labels,
        "products": products,
        "selected_product": products[0],
        "stats": request.app.state.design_stats,
        "fx_rate_label": money(rate, currency="UZS", lang=lang),
        "is_guest": request.query_params.get(
            "persona", "guest" if screen in {"catalog", "chat", "cart"} else "admin"
        )
        == "guest",
        "screen_url": screen_url,
    }
    data["preview_json"] = {
        "screen": screen,
        "variant": variant,
        "lang": lang,
        "labels": labels,
        "products": products,
        "rate": str(rate),
        "paths": SCREENS,
    }
    return f"prototype/variant_{variant.lower()}.html", data
