import re
import unicodedata
from decimal import Decimal

from app.domain.models import NormalizedQuery
from app.domain.normalize.slang import FILLER_WORDS, expand_slang
from app.domain.normalize.translit import (
    cyrillic_to_latin_uz,
    normalize_apostrophes,
)

# Common construction stopwords in Uzbek & Russian
STOPWORDS = {
    "sifatli",
    "original",
    "originali",
    "arzon",
    "aksiya",
    "skidka",
    "yangi",
    "eng",
    "yaxshi",
    "zor",
    "dostavka",
    "dostavkasi",
    "yetkazib",
    "berish",
    "новый",
    "качественный",
    "дешевый",
    "акция",
    "скидка",
    "хороший",
    "доставка",
}

# Greetings and "how much" words live with the rest of the street vocabulary;
# to this module they behave exactly like a stopword.
STOPWORDS |= FILLER_WORDS

# Unit unification dictionary
UNIT_MAP = {
    "кг": "kg",
    "kg": "kg",
    "kilo": "kg",
    "kilogram": "kg",
    "kilogramm": "kg",
    "килограмм": "kg",
    "кило": "kg",
    "dona": "dona",
    "дона": "dona",
    "шт": "dona",
    "штук": "dona",
    "sht": "dona",
    "pcs": "dona",
    "ta": "dona",
    "qop": "qop",
    "қоп": "qop",
    "мешок": "qop",
    "meshok": "qop",
    "m2": "m2",
    "м2": "m2",
    "m²": "m2",
    "kv.m": "m2",
    "кв.м": "m2",
    "kvadrat": "m2",
    "квадрат": "m2",
    "m3": "m3",
    "м3": "m3",
    "m³": "m3",
    "kub": "m3",
    "куб": "m3",
    "kub.m": "m3",
    "куб.м": "m3",
    "litr": "litr",
    "литр": "litr",
    "л": "litr",
    "l": "litr",
    "rulon": "rulon",
    "рулон": "rulon",
    "quti": "quti",
    "коробка": "quti",
    "metr": "metr",
    "метр": "metr",
    "m": "metr",
    "м": "metr",
    "sm": "sm",
    "см": "sm",
    "mm": "mm",
    "мм": "mm",
    "tonna": "tonna",
    "тонна": "tonna",
    "t": "tonna",
    "т": "tonna",
    "gramm": "gramm",
    "грамм": "gramm",
    "g": "gramm",
    "г": "gramm",
}


def unify_unit_str(unit_str: str) -> str:
    """Standardize unit text to canonical unit code."""
    cleaned = unit_str.strip().lower()
    return UNIT_MAP.get(cleaned, cleaned)


GRADE_REGEX = re.compile(
    r"\b([mмMМ])-?\s*(\d{2,3})\b|\b([aAаА])-?\s*(\d{3}[cCcС]?)\b|\b([dDдД]|Ø)\s*(\d{1,2})\b",
    re.IGNORECASE,
)
SIZE_REGEX = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*[xXхХ*×]\s*(\d+(?:\.\d+)?)(?:\s*[xXхХ*×]\s*(\d+(?:\.\d+)?))?\b"
)
DIAMETER_REGEX = re.compile(
    r"(?:Ø|диаметр\s*|diametr\s*|d\s*)(\d{1,2})(?:\s*мм|\s*mm)?", re.IGNORECASE
)
NUMBER_REGEX = re.compile(r"\b\d+(?:[.,]\d+)?\b")

# A price list prints thicknesses zero-padded to keep the column straight -- 03,
# 04, 09 -- and customers copy that across. The lookbehind protects a decimal:
# 3.05 mm is a real thickness and must not become 3.5. A word boundary will not
# serve as the closing guard: "03mm" has none between the digit and the unit.
LEADING_ZERO_REGEX = re.compile(r"(?<![\d.])0+(\d+)(?![\d.])")

# A price list writes a thickness zero-padded -- 03m, 04m, 08m -- and the
# customer copies it across. Without the zero it stays a length: "3 m" of cable
# or skirting is an ordinary thing to order, so only the padded form is
# rewritten, and it is rewritten before the zero itself is stripped.
PADDED_MM_REGEX = re.compile(r"(?<![\d.])0(\d{1,2})\s*m(?![a-z0-9])", re.IGNORECASE)

# Sheet goods are sold by a size in millimetres (1525x1525) and asked for by a
# size in metres ("1.50 na 1.50"). Both numbers being fractional is what marks
# the metre form -- a millimetre size never is.
METRE_SIZE_REGEX = re.compile(r"\b(\d\.\d{1,3})x(\d\.\d{1,3})\b")

# Plywood grade, as an experienced buyer writes it: 2/4, 3/3, 2/2. The catalog
# spells the same thing with an x. Deliberately gated on the plywood word,
# because "1/2 truba" is a half-inch pipe, and rewriting that to "1x2" would
# invent a product.
PLYWOOD_WORD_REGEX = re.compile(r"\b(?:fanera|faner|fanerka|plywood)\b")
GRADE_SLASH_REGEX = re.compile(r"\b([1-4])/([1-4])\b")


def metres_to_millimetres(match: re.Match[str]) -> str:
    """Rewrite a metre-by-metre size as the catalog's millimetre pair.

    The longer side leads, as every sheet in the price list is written --
    "1.22x2.44" and "2.44x1.22" are the same sheet, and only one of them can
    match.
    """
    first = int(round(float(match.group(1)) * 1000))
    second = int(round(float(match.group(2)) * 1000))
    longer, shorter = max(first, second), min(first, second)
    return f"{longer}x{shorter}"


def extract_grades(text: str) -> list[str]:
    grades = []
    for match in GRADE_REGEX.finditer(text):
        m_prefix, m_val, a_prefix, a_val, d_prefix, d_val = match.groups()
        if m_val:
            grades.append(f"m{m_val}")
        elif a_val:
            grades.append(f"a{a_val.lower()}")
        elif d_val:
            grades.append(f"d{d_val}")
    return grades


def extract_sizes(text: str) -> list[str]:
    sizes = []
    for match in SIZE_REGEX.finditer(text):
        parts = [p for p in match.groups() if p is not None]
        sizes.append("x".join(parts))
    return sizes


def extract_numbers(text: str) -> list[Decimal]:
    numbers = []
    for token in NUMBER_REGEX.findall(text):
        try:
            num_val = token.replace(",", ".")
            numbers.append(Decimal(num_val))
        except Exception:
            continue
    return numbers


def extract_units(text: str) -> list[str]:
    found_units = []
    tokens = text.lower().split()
    for t in tokens:
        cleaned = t.strip(".,;:()")
        if cleaned in UNIT_MAP:
            code = UNIT_MAP[cleaned]
            if code not in found_units:
                found_units.append(code)
    return found_units


def extract_stopwords(text: str) -> tuple[str, list[str]]:
    found_stopwords = []
    clean_words = []
    for word in text.split():
        w_clean = word.lower().strip(".,;:()")
        if w_clean in STOPWORDS:
            found_stopwords.append(w_clean)
        else:
            clean_words.append(word)
    return " ".join(clean_words), found_stopwords


def normalize_text(raw: str) -> str:
    """Normalize raw text query:

    1. Unicode NFKC normalization, strip, lowercase
    2. Normalize apostrophes
    3. Cyrillic -> Latin transliteration
    4. Normalize grade patterns (e.g. M-400 -> m400)
    5. Normalize size patterns (e.g. 30 х 30 -> 30x30)
    6. Normalize diameter patterns (e.g. Ø12 -> d12)
    7. Remove stopwords
    8. Whitespace collapse
    """
    if not raw:
        return ""

    # 1. NFKC & apostrophes
    nfkc = unicodedata.normalize("NFKC", raw)
    text = normalize_apostrophes(nfkc).lower().strip()

    # 2. Transliterate Cyrillic to Latin, then rewrite street vocabulary.
    # Slang runs after transliteration on purpose: one entry then covers both
    # scripts, instead of the per-word regex this step used to carry for
    # sement and shifer.
    text = cyrillic_to_latin_uz(text)
    text = expand_slang(text)

    # 3. Grade patterns
    def replace_grade(match: re.Match[str]) -> str:
        m_prefix, m_val, a_prefix, a_val, d_prefix, d_val = match.groups()
        if m_val:
            return f"m{m_val}"
        if a_val:
            return f"a{a_val.lower()}"
        if d_val:
            return f"d{d_val}"
        return match.group(0)

    text = GRADE_REGEX.sub(replace_grade, text)

    # 4. Size patterns
    def replace_size(match: re.Match[str]) -> str:
        parts = [p for p in match.groups() if p is not None]
        return "x".join(parts)

    text = SIZE_REGEX.sub(replace_size, text)

    # 5. Diameter patterns
    text = DIAMETER_REGEX.sub(r"d\1", text)

    # 5b. Sheet-goods notation: metre sizes, zero-padded thicknesses, and the
    # slash the plywood trade uses for a grade. Runs after the size pass, so a
    # size is already spelled with a single x whichever separator was typed.
    text = METRE_SIZE_REGEX.sub(metres_to_millimetres, text)
    text = PADDED_MM_REGEX.sub(r"\1mm", text)
    text = LEADING_ZERO_REGEX.sub(r"\1", text)
    if PLYWOOD_WORD_REGEX.search(text):
        text = GRADE_SLASH_REGEX.sub(r"\1x\2", text)

    # 6. Normalize punctuation
    text = re.sub(r"[-–—_]", " ", text)
    text = re.sub(r"[,;•]", " ", text)

    # 7. Extract & remove stopwords
    clean_text, _ = extract_stopwords(text)

    # 8. Collapse whitespace
    return " ".join(clean_text.split())


def normalize_query(raw: str) -> NormalizedQuery:
    """Produce structured NormalizedQuery with extracted tokens, numbers, units, etc."""
    norm_text = normalize_text(raw)
    _, stopwords = extract_stopwords(normalize_apostrophes(raw).lower())

    tokens = norm_text.split()
    numbers = extract_numbers(norm_text)
    units = extract_units(raw)
    grades = extract_grades(raw)
    sizes = extract_sizes(raw)

    return NormalizedQuery(
        raw=raw,
        text_norm=norm_text,
        tokens=tokens,
        numbers=numbers,
        units=units,
        grades=grades,
        sizes=sizes,
        stopwords=stopwords,
    )
