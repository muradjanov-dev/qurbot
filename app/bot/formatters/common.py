"""Shared display helpers for Telegram output."""

from decimal import ROUND_HALF_UP, Decimal
from html import escape as html_escape

from app.core.i18n import t


def format_uzs(amount: Decimal) -> str:
    """Render a UZS amount as '1 520 000'.

    Grouped with spaces rather than commas: a comma is a decimal separator in
    both Uzbek and Russian convention, so '1,520,000' reads wrong to the people
    actually using this bot.
    """
    whole = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{whole:,}".replace(",", " ")


def format_qty(value: Decimal) -> str:
    """Render a quantity without trailing zeros or scientific notation."""
    return format(value.normalize(), "f")


def esc(value: object) -> str:
    """Escape text that came from a user before putting it in an HTML message.

    The bot sends with ParseMode.HTML, so any '<' a user types is parsed as
    markup. An unclosed tag makes Telegram reject the whole message with
    "can't parse entities", which looks to that user like the bot is broken --
    so this is about the bot staying usable, not only about injection.
    """
    return html_escape(str(value), quote=False)


def format_catalog_price(
    live_price: Decimal | None,
    reference_price: Decimal | None,
    *,
    lang: str = "uz_latn",
) -> str:
    """Render the price to show against a catalogue row.

    Three cases, in the order they are trusted. A live shop offer is a price
    someone will honour today, so it is shown plainly. Failing that the
    supplier's list price is shown prefixed with '~', because a list price
    moves with the order day and must not read as a firm quote. With neither,
    the price list itself said the price is agreed per order.
    """
    if live_price is not None:
        return f"{format_uzs(live_price)} {t('currency_suffix', lang=lang)}"
    if reference_price is not None:
        return f"~{format_uzs(reference_price)} {t('currency_suffix', lang=lang)}"
    return t("price_negotiable", lang=lang)
