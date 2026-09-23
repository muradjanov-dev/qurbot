"""Shared display helpers for Telegram output."""

from decimal import ROUND_HALF_UP, Decimal
from html import escape as html_escape

from app.core.i18n import DEFAULT_LANG, t
from app.domain.normalize.translit import latin_to_cyrillic_uz


def format_uzs(amount: Decimal) -> str:
    """Render a whole-UZS amount with dot thousands groups."""
    whole = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{whole:,}".replace(",", ".")


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


def shorten_button_label(text: str, limit: int) -> str:
    """Fit a product name into an inline button without losing what identifies it.

    Telegram gives a button one line and clips whatever does not fit, from the
    right -- which on these names throws away the size, the only part that
    tells two rows apart. "Krovelniy samorez oq (metallga) 6.3x25-200" arrived
    on a phone as "Krovelniy samorez oq (metall", and the customer was asked to
    choose between three buttons that read the same.

    So the family word is kept and the middle is dropped instead, taking as
    much of the tail as will fit. What survives is what a buyer is choosing
    between: "Fanera… SiyPly 18 mm (2440x1220)", "Krovelniy… (metallga)
    6.3x25-200". Cutting from the right instead would leave both of those as
    the word they share.
    """
    text = " ".join(text.split())
    if len(text) <= limit:
        return text

    words = text.split(" ")
    head = words[0]
    budget = limit - len(head) - 2  # the ellipsis and the space after it
    if budget <= 0:
        return text[:limit]

    tail_words: list[str] = []
    for word in reversed(words[1:]):
        candidate = [word, *tail_words]
        if len(" ".join(candidate)) > budget:
            break
        tail_words = candidate
    if not tail_words:
        return f"{head}… {words[-1][-budget:]}"
    return f"{head}… {' '.join(tail_words)}"


def format_catalog_price(
    live_price: Decimal | None,
    reference_price: Decimal | None,
    *,
    lang: str = DEFAULT_LANG,
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


def localized_name(
    name_uz: str,
    name_ru: str,
    lang: str,
    *,
    name_uz_cyrl: str | None = None,
) -> str:
    """Pick the right spelling of a catalogue or geography name for `lang`.

    Only two of the three scripts are ever stored: districts and categories
    carry `name_uz` and `name_ru`, and canonical products additionally carry a
    hand-written `name_uz_cyrl`. Without this helper every call site fell back
    to the Latin name for a Cyrillic reader, so a customer who picked Ўзбекча
    got a district list and product cards in Latin -- the one place the bot
    visibly forgot which language it was speaking.

    Where no Cyrillic spelling is stored the Latin one is transliterated. That
    is exact for Uzbek place names ("Mirzo Ulug'bek" -> "Мирзо Улуғбек"), which
    is what the district list needs; a product with an editorial Cyrillic name
    should pass `name_uz_cyrl` so the stored spelling wins over the mechanical
    one.
    """
    if lang == "ru":
        return name_ru
    if lang == "uz_cyrl":
        return name_uz_cyrl or latin_to_cyrillic_uz(name_uz)
    return name_uz
