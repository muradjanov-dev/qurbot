"""Shared display helpers for Telegram output."""

from decimal import ROUND_HALF_UP, Decimal
from html import escape as html_escape


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
