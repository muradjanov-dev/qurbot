"""Render a product listing for Telegram.

The card layout is deliberately identical whether the viewer is the shop owner
reviewing their own draft or a customer browsing -- one layout to maintain, and
owners see exactly what buyers will see before they save.
"""

from decimal import Decimal
from html import escape

from app.bot.formatters.common import format_qty, format_uzs
from app.core.i18n import t
from app.domain.listing import ListingCard, ListingDraft, StockDisplay

_STOCK_KEYS = {
    StockDisplay.IN_STOCK: "listing_stock_in_stock",
    StockDisplay.LOW: "listing_stock_low",
    StockDisplay.ON_ORDER: "listing_stock_on_order",
    StockDisplay.OUT: "listing_stock_out",
}

DIVIDER = "──────────────────────────────"


def render_listing_card(card: ListingCard, lang: str, *, show_shop: bool = True) -> str:
    """One product, formatted for a Telegram message with HTML parse mode."""
    parts: list[str] = []

    title = escape(card.title)
    if card.brand:
        title = f"{title} · {escape(card.brand)}"
    parts.append(f"📦 <b>{title}</b>")

    if show_shop and card.shop_name:
        parts.append(f"🏪 {escape(card.shop_name)}")

    if card.description:
        parts.append(f"\n<i>{escape(card.description)}</i>")

    if card.attributes:
        attr_text = " · ".join(f"{escape(k)}: {escape(v)}" for k, v in card.attributes)
        parts.append(f"\n🔧 {attr_text}")

    parts.append("")
    price_label = t("listing_label_price", lang=lang)
    parts.append(
        f"💰 <b>{price_label}:</b> {format_uzs(card.price_per_pack)} so'm"
        f" / {escape(card.pack_label)}"
    )

    unit_label = t("listing_label_unit_price", lang=lang, unit=escape(card.base_unit))
    parts.append(f"    <i>{unit_label}: {format_uzs(card.price_per_base_unit)} so'm</i>")

    stock_text = t(_STOCK_KEYS[card.stock], lang=lang)
    if card.stock_qty is not None and card.stock is not StockDisplay.OUT:
        stock_text = f"{stock_text} ({format_qty(card.stock_qty)})"
    parts.append(f"📊 {stock_text}")

    if card.has_photos:
        photo_label = t("listing_label_photos", lang=lang)
        parts.append(f"📷 {photo_label}: {len(card.photos)}")

    return "\n".join(parts)


def render_draft_review(
    draft: ListingDraft,
    lang: str,
    *,
    card: ListingCard,
    matched_name: str | None,
) -> str:
    """The confirmation screen shown before a draft becomes a live offer."""
    header = t("listing_review_title", lang=lang)
    body = render_listing_card(card, lang=lang, show_shop=False)

    footer: list[str] = []
    if matched_name:
        footer.append(t("listing_matched_as", lang=lang, name=escape(matched_name)))
    else:
        footer.append(t("listing_not_matched", lang=lang))

    footer_text = "\n".join(footer)
    return f"{header}\n\n{body}\n\n{DIVIDER}\n{footer_text}"


def render_saved_confirmation(name: str, lang: str, *, media_pending: bool) -> str:
    text = t("listing_saved", lang=lang, name=escape(name))
    if media_pending:
        text = f"{text}\n<i>{t('listing_saved_pending_media', lang=lang)}</i>"
    return text


def format_price_hint(price_per_pack: Decimal, pack_label_text: str) -> str:
    return f"{format_uzs(price_per_pack)} so'm / {pack_label_text}"
