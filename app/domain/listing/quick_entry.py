"""Read a whole product listing out of one line of text.

A shop owner types what they would say out loud -- "Sement M400 50kg qop 52000"
-- and this turns it into name, pack, price and quantity so the bot does not
have to ask four separate questions.

The one rule that shapes everything here: **a price is never guessed silently.**
Numbers get claimed in order of how certain their meaning is -- glued to letters
(a grade), bound to a unit (a pack), marked with a currency word (a price) --
and only a genuinely free-standing number is offered up as a probable price,
flagged `price_is_explicit=False` so the caller confirms it before saving.
Getting this wrong is not a cosmetic bug: the price feeds price_per_base_unit,
which decides every quote the shop appears in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.domain.normalize.text import UNIT_MAP

# Units that describe how much is in a pack. Deliberately excludes mm/sm:
# "Gipsokarton 12.5mm" is a thickness, not a pack of 12.5 millimetres, and
# reading it as a pack would corrupt the unit price.
_DIMENSIONAL_UNITS = frozenset({"kg", "tonna", "gramm", "litr", "m2", "m3", "metr"})
# Packaging words -- meaningful as a pack only when nothing dimensional is given.
_CONTAINER_UNITS = frozenset({"qop", "dona", "quti", "rulon"})
_PACK_UNITS = _DIMENSIONAL_UNITS | _CONTAINER_UNITS

_PRICE_WORDS = r"so'm|so`m|som|sum|сум|сўм|uzs"
_PRICE_LABELS = r"narx(?:i)?|цена|price|стоимость"
_QTY_LABELS = r"qoldiq|mavjud|zapas|ostatok|остаток|количество|soni"

_NUM = r"\d+(?:[.,]\d+)?"

# Anything matched here is a product attribute: its digits are protected from
# being read as a price or a pack, but the text stays in the product name --
# "M400" and "30x30" are how the customer recognises the product.
# The letter prefix is capped at three characters and may not be separated by a
# space, so "Sement 50" is not mistaken for a grade the way "M400" is.
_ATTRIBUTE_PATTERNS = (
    re.compile(r"\b[a-zA-Zа-яёА-ЯЁ]{1,3}-?\d+(?:[.,]\d+)?\b", re.IGNORECASE),  # M400, d12
    re.compile(rf"{_NUM}\s*[xх×*]\s*{_NUM}", re.IGNORECASE),  # 30x30
    re.compile(rf"{_NUM}\s*(?:mm|мм|sm|см)\b", re.IGNORECASE),  # 12.5mm
)

_UNIT_ALTERNATION = "|".join(sorted((re.escape(k) for k in UNIT_MAP), key=len, reverse=True))

_EXPLICIT_PRICE_PATTERNS = (
    re.compile(rf"({_NUM})\s*(?:{_PRICE_WORDS})\b", re.IGNORECASE),
    re.compile(rf"(?:{_PRICE_LABELS})\s*[:=-]?\s*({_NUM})", re.IGNORECASE),
    re.compile(rf"=\s*({_NUM})"),
)
_QTY_LABEL_PATTERN = re.compile(rf"(?:{_QTY_LABELS})\s*[:=-]?\s*({_NUM})", re.IGNORECASE)
_NUM_UNIT_PATTERN = re.compile(
    rf"({_NUM})\s*({_UNIT_ALTERNATION})(?![a-zA-Zа-яёА-ЯЁ0-9])", re.IGNORECASE
)
_BARE_NUM_PATTERN = re.compile(rf"(?<![\w.,]){_NUM}(?![\w.,])")

# Below this, a bare number is far more likely to be a count, a size or a
# model number than a UZS price -- nothing in this catalogue costs 40 so'm.
MIN_INFERRED_PRICE = Decimal("100")


@dataclass(frozen=True)
class ParsedListingInput:
    name: str
    price: Decimal | None
    price_is_explicit: bool
    pack_size: Decimal | None
    pack_unit: str | None
    stock_qty: Decimal | None

    @property
    def is_actionable(self) -> bool:
        """Whether this is worth treating as a product at all."""
        return bool(self.name.strip())

    @property
    def needs_price_confirmation(self) -> bool:
        return self.price is not None and not self.price_is_explicit


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None


class _SpanClaims:
    """Tracks how each character of the caption has been interpreted.

    Two distinct notions, which is the whole point: *reserved* means "already
    explained, do not read this as something else", while *consumed* means
    "extracted into a field, drop it from the name". A grade like M400 is
    reserved but not consumed -- it must not be mistaken for a price, yet it
    still belongs in the product name.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.reserved = [False] * len(text)
        self.consumed = [False] * len(text)

    def is_free(self, start: int, end: int) -> bool:
        return not any(self.reserved[start:end])

    def reserve(self, start: int, end: int) -> None:
        for i in range(start, min(end, len(self.reserved))):
            self.reserved[i] = True

    def claim(self, start: int, end: int) -> None:
        self.reserve(start, end)
        for i in range(start, min(end, len(self.consumed))):
            self.consumed[i] = True

    def remaining(self) -> str:
        kept = "".join(char for idx, char in enumerate(self.text) if not self.consumed[idx])
        return re.sub(r"\s+", " ", kept).strip(" .,;:-\n\t")


def parse_listing_caption(caption: str) -> ParsedListingInput:
    """Extract a listing from free text. Never raises; unknown parts come back None."""
    text = (caption or "").strip()
    if not text:
        return ParsedListingInput(
            name="",
            price=None,
            price_is_explicit=False,
            pack_size=None,
            pack_unit=None,
            stock_qty=None,
        )

    spans = _SpanClaims(text)

    # 1. Reserve product attributes first so their digits can never be claimed
    #    as a price or a pack size.
    for pattern in _ATTRIBUTE_PATTERNS:
        for match in pattern.finditer(text):
            # A unit that happens to look like an attribute ("m2", "m3") must
            # stay available as a pack unit.
            if UNIT_MAP.get(match.group(0).lower().replace(" ", "")):
                continue
            if spans.is_free(*match.span()):
                spans.reserve(*match.span())

    # 2. An explicitly marked price is the most certain reading available.
    price: Decimal | None = None
    price_is_explicit = False
    for pattern in _EXPLICIT_PRICE_PATTERNS:
        for match in pattern.finditer(text):
            value = _to_decimal(match.group(1))
            if value is None or value <= 0:
                continue
            price = value
            price_is_explicit = True
            spans.claim(*match.span())
            break
        if price is not None:
            break

    # 3. A labelled quantity is likewise unambiguous.
    stock_qty: Decimal | None = None
    for match in _QTY_LABEL_PATTERN.finditer(text):
        if not spans.is_free(*match.span()):
            continue
        value = _to_decimal(match.group(1))
        if value is None or value < 0:
            continue
        stock_qty = value
        spans.claim(*match.span())
        break

    # 4. Number bound to a unit: the dimensional one is the pack, because it is
    #    the only one that can express a comparable per-unit price. A count unit
    #    seen afterwards can then only be "how many packs".
    pack_size: Decimal | None = None
    pack_unit: str | None = None
    container_candidates: list[tuple[Decimal, str, tuple[int, int]]] = []

    for match in _NUM_UNIT_PATTERN.finditer(text):
        if not spans.is_free(*match.span()):
            continue
        value = _to_decimal(match.group(1))
        if value is None or value <= 0:
            continue
        unit = UNIT_MAP.get(match.group(2).lower())
        if unit is None or unit not in _PACK_UNITS:
            continue
        if unit in _DIMENSIONAL_UNITS and pack_size is None:
            pack_size, pack_unit = value, unit
            spans.claim(*match.span())
        elif unit in _CONTAINER_UNITS:
            container_candidates.append((value, unit, match.span()))

    for value, unit, span in container_candidates:
        if not spans.is_free(*span):
            continue
        if pack_size is None:
            pack_size, pack_unit = value, unit
            spans.claim(*span)
        elif stock_qty is None:
            stock_qty = value
            spans.claim(*span)

    # 5. Whatever free-standing number is left is a probable price -- offered,
    #    but marked as inferred so the caller confirms before it is stored.
    if price is None:
        candidates: list[tuple[Decimal, tuple[int, int]]] = []
        for match in _BARE_NUM_PATTERN.finditer(text):
            if not spans.is_free(*match.span()):
                continue
            value = _to_decimal(match.group(0))
            if value is None or value < MIN_INFERRED_PRICE:
                continue
            candidates.append((value, match.span()))
        if candidates:
            best = max(candidates, key=lambda pair: pair[0])
            price = best[0]
            price_is_explicit = False
            spans.claim(*best[1])

    return ParsedListingInput(
        name=spans.remaining(),
        price=price,
        price_is_explicit=price_is_explicit,
        pack_size=pack_size,
        pack_unit=pack_unit,
        stock_qty=stock_qty,
    )
