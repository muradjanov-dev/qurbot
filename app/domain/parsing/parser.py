import re
from decimal import Decimal

from app.domain.normalize.slang import strip_fillers
from app.domain.normalize.text import (
    normalize_text,
    protect_decimal_commas,
    unify_unit_str,
)
from app.domain.parsing.models import ParsedLine

# Line start bullets or numbering: "1.", "1)", "•", "-", "*"
# (requires space + non-digit after number prefix)
# A hyphen only counts as a bullet when whitespace follows it: "- 10 qop" is a
# list item, but "-10 qop" is a negative quantity, and stripping the sign there
# turned a customer's mistake into a real order for the positive amount.
LINE_PREFIX_REGEX = re.compile(r"^\s*(?:[\d]+[\.\)](?=\s+[^\d])|[•*]|-(?=\s))\s*")

# Known unit regex tokens
UNIT_TOKENS = (
    r"dona|дона|шт|штук|sht|pcs|ta|list|лист|qop|қоп|мешок|meshok|m2|м2|m²|kv\.m|кв\.м|kvadrat|квадрат|"
    r"m3|м3|m³|kub|куб|kub\.m|куб\.м|litr|литр|л|l|rulon|рулон|quti|коробка|кор|korobka|"
    r"pachka|пачка|пач|pach|upakovka|упаковка|metr|метр|m|м|"
    r"sm|см|mm|мм|tonna|тонна|t|т|kg|кг|kilo|кило|килограмм|gramm|грамм|g|г"
)

# Range pattern: e.g. "10-15" or "10 - 15" or "10..15"
# "10-15 qop" is a range. "1.5x1.5 - 15 ta" is a size and a quantity, and
# reading it as a range produced 1500x1150 -- a sheet nobody makes -- and ate
# the quantity on the way. The lookbehind keeps the range syntax away from
# anything that is already part of a size.
RANGE_REGEX = re.compile(r"(?<![xх×*\d.])\b(\d+(?:\.\d+)?)\s*(?:[-–—]|\.{2})\s*(\d+(?:\.\d+)?)\b")

# Multiplier pattern: e.g. "5 x 10 qop"
MULTIPLIER_REGEX = re.compile(
    rf"^\s*(\d+(?:\.\d+)?)\s*[xX*×]\s*(\d+(?:\.\d+)?)\s*({UNIT_TOKENS})",
    re.IGNORECASE,
)

# Pattern: e.g. "3 vedra 10l" -> 30l
CONTAINER_VOL_REGEX = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:vedra|vedro|chelak|банка|канистра|бочка|quti|idish)\s*(\d+(?:\.\d+)?)\s*(l|litr|л|литр|kg|кг)",
    re.IGNORECASE,
)

# Regex 1: Qty (+ unit) at beginning: e.g. "500 dona g'isht", "10 qop sement", "2t qum"
QTY_START_REGEX = re.compile(
    rf"^\s*(-?\d+(?:\.\d+)?)\s*({UNIT_TOKENS})?\b\s*(?:ta\s+)?(?:\bta\b)?\s*[:-]?\s*(.*)$",
    re.IGNORECASE,
)

# Regex 2: Qty (+ unit) at end: e.g. "sement m400 - 20 qop", "armatura 12mm 500 kg"
QTY_END_REGEX = re.compile(
    rf"^(.*)\s*(?:[:-]\s*|\s+)(\d+(?:\.\d+)?)\s*({UNIT_TOKENS})\s*$",
    re.IGNORECASE,
)


# "500 dona kirpich va 2 tonna pesok" is two orders in one breath, and nothing
# else in the message says so -- no comma, no newline. Left joined, the second
# product is swallowed into the first line's name and quietly never ordered,
# which is worse than failing to match it.
CONJUNCTION_REGEX = re.compile(r"\s+(?:va|ва|и|and)\s+", re.IGNORECASE)
DIGIT_REGEX = re.compile(r"\d")


def split_on_conjunctions(text: str) -> list[str]:
    """Split on "and" only when every part stands alone as an order line.

    The test is the parser itself: each half must yield a quantity through the
    same regex battery a real line goes through. That is what separates two
    orders ("500 dona kirpich va 2 tonna pesok") from prose that merely
    contains the word -- "faneradan 10ta va osbdan 5ta kerak edi" reads like
    two items but neither half parses, and splitting it would strand the
    remainder as junk instead of letting the whole message reach the LLM
    parser, which can actually read it.
    """
    parts = CONJUNCTION_REGEX.split(text)
    if len(parts) < 2:
        return [text]

    stripped = [part.strip() for part in parts]
    if not all(part and DIGIT_REGEX.search(part) for part in stripped):
        return [text]
    if not all(not parse_single_line(0, part).needs_review for part in stripped):
        return [text]
    return stripped


def split_message_to_lines(raw_text: str) -> list[str]:
    """Split a free-text order into individual item lines while protecting numeric decimals."""
    if not raw_text or not raw_text.strip():
        return []

    # 1. Protect numeric commas
    protected = protect_decimal_commas(raw_text)

    # 2. Split on newlines and semicolons
    raw_lines: list[str] = []
    for chunk in re.split(r"[\n;]", protected):
        chunk = chunk.strip()
        if not chunk:
            continue
        # Also split by commas (now that decimal commas are protected), then by
        # a spoken "and" joining two quantified items.
        for sub in chunk.split(","):
            sub_clean = sub.strip()
            if sub_clean:
                raw_lines.extend(split_on_conjunctions(sub_clean))

    # 3. Clean line prefixes (e.g. "1. ", "• ")
    clean_lines = []
    for line in raw_lines:
        line_clean = LINE_PREFIX_REGEX.sub("", line).strip()
        if line_clean:
            clean_lines.append(line_clean)

    return clean_lines


# Units that count things you can put on a lorry. A dimension is not one of
# them: nobody orders "3 mm" of plywood, and reading a thickness as the
# quantity is how "03m 10ta fanera" became three metres of "10ta fanera".
COUNT_UNIT_TOKENS = (
    r"dona|дона|шт|штук|sht|pcs|ta|qop|қоп|мешок|meshok|rulon|рулон|quti|коробка|кор|"
    r"pachka|пачка|пач|list|лист"
)
COUNT_ANYWHERE_REGEX = re.compile(rf"\b(\d+(?:\.\d+)?)\s*({COUNT_UNIT_TOKENS})\b", re.IGNORECASE)

# "03m ...", "12mm ..." -- a line that opens with a measurement, not an amount.
STARTS_WITH_DIMENSION_REGEX = re.compile(
    r"^\s*\d+(?:\.\d+)?\s*(?:mm|мм|sm|см|m|м)\b", re.IGNORECASE
)


def find_counted_quantity(text: str) -> tuple[Decimal, str, str] | None:
    """A "10 ta"-shaped quantity anywhere in the line, and the line without it.

    The price list puts the thickness first -- "03m 10ta fanera" -- so the
    first number on the line is routinely not the amount being ordered. A
    counting unit is unambiguous in a way position is not, so when one is
    present it wins, and what remains is the product.
    """
    match = COUNT_ANYWHERE_REGEX.search(text)
    if match is None:
        return None
    remainder = (text[: match.start()] + " " + text[match.end() :]).strip()
    if not remainder:
        return None
    return Decimal(match.group(1)), unify_unit_str(match.group(2)), remainder


def parse_single_line(line_no: int, raw_line: str) -> ParsedLine:
    """Parse a single text line into structured (parsed_name, qty, unit_code)."""
    # Greetings come off before the quantity regexes run: those anchor on the
    # start of the line, so "aka menga 10 qop sement" extracted no quantity at
    # all until "aka menga" was gone -- and a basket where no line carries a
    # quantity is what sends the whole message to the LLM.
    text = strip_fillers(protect_decimal_commas(raw_line).strip())
    needs_review = False
    user_note: str | None = None

    # A line that opens with a dimension is the price list's own order --
    # "03m 10ta fanera" is three millimetres, ten sheets. Position says the
    # first number is the amount; the counting unit says otherwise, and it is
    # the one that cannot be misread. Narrow on purpose: every other line keeps
    # the rules below, including negative amounts, ranges and multipliers,
    # which a broader version of this quietly broke.
    counted = find_counted_quantity(text) if STARTS_WITH_DIMENSION_REGEX.match(text) else None
    if counted is not None:
        counted_qty, counted_unit, remainder = counted
        return ParsedLine(
            line_no=line_no,
            raw_text=raw_line,
            parsed_name=normalize_text(remainder),
            qty=counted_qty,
            unit_code=counted_unit,
            confidence=0.95,
            needs_review=False,
        )

    # Check for container * volume pattern: e.g. "kraska belaya 3 vedra 10l"
    container_match = CONTAINER_VOL_REGEX.search(text)
    if container_match:
        count_val = Decimal(container_match.group(1))
        vol_val = Decimal(container_match.group(2))
        vol_unit = container_match.group(3)
        total_qty = count_val * vol_val
        vol_unit_code = unify_unit_str(vol_unit)

        # Remove the container part from text
        prod_text = text[: container_match.start()] + " " + text[container_match.end() :]
        parsed_name = normalize_text(prod_text)
        return ParsedLine(
            line_no=line_no,
            raw_text=raw_line,
            parsed_name=parsed_name,
            qty=total_qty,
            unit_code=vol_unit_code,
            confidence=0.95,
            needs_review=needs_review,
            user_note=user_note,
        )

    # Check for range: e.g. "10-15 qop" (must have v1 < v2)
    range_match = RANGE_REGEX.search(text)
    if range_match:
        v1 = Decimal(range_match.group(1))
        v2 = Decimal(range_match.group(2))
        if v1 < v2:
            upper_val = v2
            needs_review = True
            user_note = f"Range specified: {range_match.group(0)} (upper bound selected)"
            text = text[: range_match.start()] + str(upper_val) + text[range_match.end() :]

    # Check for multiplier: e.g. "5 x 10 qop"
    mult_match = MULTIPLIER_REGEX.match(text)
    if mult_match:
        v1 = Decimal(mult_match.group(1))
        v2 = Decimal(mult_match.group(2))
        u = mult_match.group(3)
        total = v1 * v2
        text = f"{total} {u} " + text[mult_match.end() :]

    # 1. Try QTY_START_REGEX: e.g. "500 dona g'isht" or "2t qum"
    start_match = QTY_START_REGEX.match(text)
    if start_match:
        qty_str, unit_raw, product_phrase = start_match.groups()
        qty = Decimal(qty_str)
        unit_code: str | None = unify_unit_str(unit_raw) if unit_raw else None
        if unit_raw and unit_raw.lower() in ["list", "лист", "ta"]:
            unit_code = "dona"
        parsed_name = normalize_text(product_phrase)
        if not unit_code:
            needs_review = True
        return ParsedLine(
            line_no=line_no,
            raw_text=raw_line,
            parsed_name=parsed_name if parsed_name else normalize_text(raw_line),
            qty=qty,
            unit_code=unit_code,
            confidence=0.95 if unit_code else 0.70,
            needs_review=needs_review,
            user_note=user_note,
        )

    # 2. Try QTY_END_REGEX: e.g. "sement m400 - 20 qop" or "armatura 12mm 500 kg"
    end_match = QTY_END_REGEX.match(text)
    if end_match:
        product_phrase, qty_str, unit_raw = end_match.groups()
        qty = Decimal(qty_str)
        unit_code = unify_unit_str(unit_raw)
        if unit_raw.lower() in ["list", "лист", "ta"]:
            unit_code = "dona"
        parsed_name = normalize_text(product_phrase)
        return ParsedLine(
            line_no=line_no,
            raw_text=raw_line,
            parsed_name=parsed_name if parsed_name else normalize_text(raw_line),
            qty=qty,
            unit_code=unit_code,
            confidence=0.95,
            needs_review=needs_review,
            user_note=user_note,
        )

    # Fallback: Default to 1 unit with needs_review=True
    parsed_name = normalize_text(text)
    return ParsedLine(
        line_no=line_no,
        raw_text=raw_line,
        parsed_name=parsed_name,
        qty=Decimal("1"),
        unit_code=None,
        confidence=0.50,
        needs_review=True,
        user_note="Quantity or unit not explicitly specified",
    )


# A quantity must be orderable to be worth pricing. The ceiling is injected
# rather than hard-coded so the caller supplies the configured limit; the
# default keeps this module usable (and testable) on its own.
DEFAULT_MAX_QTY = Decimal("1000000")


def is_qty_orderable(qty: Decimal, max_qty: Decimal = DEFAULT_MAX_QTY) -> bool:
    """Whether this quantity is something a customer could actually order.

    Zero and negative quantities are input errors -- there is no such order --
    and a quantity above the ceiling is a typo whose total would be
    meaningless. Both are refused rather than silently clamped, so the
    customer sees what was wrong instead of an unexpected number.
    """
    return Decimal("0") < qty <= max_qty


def parse_basket_lines(raw_text: str) -> list[ParsedLine]:
    """Parse complete basket text into a sequence of ParsedLine objects."""
    split_lines = split_message_to_lines(raw_text)
    parsed: list[ParsedLine] = []
    for idx, line in enumerate(split_lines, start=1):
        parsed.append(parse_single_line(idx, line))
    return parsed
