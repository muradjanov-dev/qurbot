"""Street vocabulary -> the wording the catalog actually uses.

Customers do not write catalog names. They write the Russian trade word
("kirpich"), the phonetic spelling they grew up with ("shipr"), and wrap it in
the words you would use talking to a shopkeeper ("aka menga ... kere"). None of
that scores against `search_doc`, which stores the Uzbek Latin name -- so
without this pass the most common phrasing takes the slowest and least certain
path through matching, the LLM.

Two deliberate choices:

* **A dictionary, not a prompt.** These mappings are the same on every run,
  cost nothing, and answer in microseconds. The LLM is for what is left after
  this, not for "kirpich means g'isht".
* **Applied after transliteration.** By the time `expand_slang` runs the text
  is already Latin, so one entry covers "кирпич" and "kirpich" both, and the
  map does not need a Cyrillic twin for every line.

Entries map jargon onto the vocabulary the seeded categories use (sement,
g'isht, armatura, taxta, bo'yoq, plitka, quvur, izolyatsiya, gipsokarton) --
this is a language mapping, not a product list, and it invents no SKUs.
"""

from __future__ import annotations

import re

from app.domain.normalize.translit import cyrillic_to_latin_uz, normalize_apostrophes

# Jargon -> catalog wording. Keys are post-transliteration Latin, lowercase.
# No value may also be a key: expansion must settle in a single pass, or a
# second call would rename a product that was already correct.
PRODUCT_SLANG: dict[str, str] = {
    # Sement va qorishmalar
    "tsement": "sement",
    "rastvor": "qorishma",
    "alebastr": "gips",
    "izvest": "ohak",
    "shpaklevka": "shpaklovka",
    "shpaklyovka": "shpaklovka",
    "shpatlyovka": "shpaklovka",
    "gruntovka": "grunt",
    "kley": "yelim",
    "klei": "yelim",
    "yopishtiruvchi": "yelim",
    # G'isht, bloklar, inert materiallar
    "kirpich": "g'isht",
    "kirpech": "g'isht",
    "pesok": "qum",
    "shcheben": "shag'al",
    "shchebenka": "shag'al",
    "shchebyonka": "shag'al",
    "shebenka": "shag'al",
    "graviy": "shag'al",
    # Metall va armatura
    "armatur": "armatura",
    "gvozd": "mix",
    "gvozdi": "mix",
    "provoloka": "sim",
    "setka rabitsa": "rabitsa to'r",
    "setka": "to'r",
    "truba": "quvur",
    "truby": "quvur",
    # Yog'och
    "doska": "taxta",
    "doski": "taxta",
    # Bo'yoq va lak
    "kraska": "bo'yoq",
    "kraski": "bo'yoq",
    "rastvoritel": "erituvchi",
    # Elektr
    "provod": "sim",
    "provoda": "sim",
    "lampochka": "lampa",
    # Izolyatsiya
    "uteplitel": "izolyatsiya",
    # Gipsokarton
    "gkl": "gipsokarton",
    "gipskarton": "gipsokarton",
    "gipsakarton": "gipsokarton",
    # Tom yopish -- phonetic spellings of shifer that reach us constantly
    "shipr": "shifer",
    "shifr": "shifer",
    # Mahkamlash materiallari (metiz). The fastener trade is spoken in Russian
    # nouns that get an Uzbek plural, a Russian plural, or neither depending on
    # who is typing -- "anker", "ankera" and "ankerlar" are one word in three
    # coats, and only the bare stem is on the price list.
    #
    # The supplier's own spellings are here too, mapped the other way round:
    # the list prints "ПОТТАЙ", "ПРОПКА" and "САРИК" where the words are potay,
    # probka and sariq, and the catalogue carries the correct spelling.
    "ankera": "anker",
    "ankeri": "anker",
    "ankerlar": "anker",
    "samarez": "samorez",
    "samorezi": "samorez",
    "samorezy": "samorez",
    "samorezlar": "samorez",
    "shurup": "samorez",
    "shurupy": "samorez",
    "shuruplar": "samorez",
    "bolty": "bolt",
    "boltlar": "bolt",
    "gayki": "gayka",
    "gaykalar": "gayka",
    "shayby": "shayba",
    "shaybalar": "shayba",
    "shpilki": "shpilka",
    "shpilkalar": "shpilka",
    "kryuchki": "kryuchok",
    "kryuchkov": "kryuchok",
    "kryuchoklar": "kryuchok",
    "ilmoq": "kryuchok",
    "dubel": "dyubel",
    "dyubeli": "dyubel",
    "dyubelya": "dyubel",
    "dyubellar": "dyubel",
    "zaklyopka": "zaklepka",
    "zaklyopki": "zaklepka",
    "zaklepki": "zaklepka",
    "chopiq": "chopik",
    "chopiqlar": "chopik",
    "glukhar": "gluxar",
    "krovelnyy": "krovelniy",
    "krovelny": "krovelniy",
    "krovelnaya": "krovelniy",
    "pottay": "potay",
    "propka": "probka",
    "styajka": "stashka",
    "sarik": "sariq",
    "kora samorez": "qora samorez",
    # Ranglar. A colour is half of how a customer names brick, paint or tile
    # ("krasniy kirpich"), and the catalog writes it in Uzbek, so the Russian
    # adjective has to cross over with the noun or the line scores worse than
    # if it had been left out.
    #
    # Both spellings of each ending are here on purpose: transliterating
    # "красный" yields "krasnyy", but a customer typing Latin writes "krasniy",
    # and only one of those two ever reaches this map per message.
    "belyy": "oq",
    "beliy": "oq",
    "belaya": "oq",
    "beloe": "oq",
    "chernyy": "qora",
    "cherniy": "qora",
    "chyornyy": "qora",
    "chorniy": "qora",
    "chernaya": "qora",
    "chyornaya": "qora",
    "krasnyy": "qizil",
    "krasniy": "qizil",
    "krasnaya": "qizil",
    "siniy": "ko'k",
    "sinyaya": "ko'k",
    "zelenyy": "yashil",
    "zeleniy": "yashil",
    "zelyonyy": "yashil",
    "zelenaya": "yashil",
    "zelyonaya": "yashil",
    "seryy": "kulrang",
    "seriy": "kulrang",
    "seraya": "kulrang",
    "jeltyy": "sariq",
    "jeltiy": "sariq",
    "jyoltyy": "sariq",
    "korichnevyy": "jigarrang",
    "korichneviy": "jigarrang",
}

# Words that carry a request but never a product: greetings, politeness, "how
# much", "send me". They are deleted rather than mapped -- a customer writing
# "aka menga 10 qop tsement kere" is ordering cement, and every extra token
# dilutes the trigram score of the word that matters.
#
# Nothing here may appear in PRODUCT_SLANG (asserted in tests): deleting a word
# that names a product would silently drop the order line.
FILLER_WORDS: frozenset[str] = frozenset(
    {
        # Murojaat va odob
        "salom",
        "assalomu",
        "alaykum",
        "rahmat",
        "iltimos",
        "hurmatli",
        "aka",
        "uka",
        "opa",
        "usta",
        "boss",
        "xo'jayin",
        "brat",
        "bratan",
        # So'rov
        "menga",
        "bizga",
        "kere",
        "kerak",
        "kerakedi",
        "keragi",
        "bormi",
        "bormidi",
        "bo'ladimi",
        "zakaz",
        "yubor",
        "yuboring",
        "tashla",
        "tashlang",
        "ber",
        "bering",
        "beringlar",
        "bervor",
        "bervoring",
        "olib",
        "kelsin",
        # Narx so'rash
        "narx",
        "narxi",
        "qancha",
        "qanchadan",
        "pochom",
        "pochyom",
        # Ruscha
        "nado",
        "nujno",
        "skolko",
        "pojaluysta",
        "davay",
        "privet",
        "spasibo",
    }
)

# Longest key first, so "setka rabitsa" is claimed before the bare "setka".
# The boundaries reject a key that is only part of a longer word ("kirpichniy")
# and treat the apostrophe as a letter, since it carries meaning in Uzbek.
_SLANG_PATTERN = re.compile(
    r"(?<![\w'])("
    + "|".join(re.escape(key) for key in sorted(PRODUCT_SLANG, key=len, reverse=True))
    + r")(?![\w'])",
    re.IGNORECASE,
)

_STRIP_CHARS = ".,;:!?()"


def expand_slang(text: str) -> str:
    """Rewrite street vocabulary into catalog wording, leaving everything else alone."""
    if not text:
        return text
    return _SLANG_PATTERN.sub(lambda m: PRODUCT_SLANG[m.group(1).lower()], text)


def strip_fillers(text: str) -> str:
    """Drop greeting/politeness words so a quantity can lead the line again.

    The quantity regexes in the parser anchor on the start of the line, so
    "aka menga 10 qop sement" parsed as no quantity at all until the two words
    in front were removed. Tokens are compared after transliteration, which
    catches the Cyrillic spelling of the same word without a second word list.

    A line that is nothing but filler is returned untouched: better to hand the
    parser a greeting it will reject than an empty string it cannot report on.
    """
    if not text or not text.strip():
        return text

    kept: list[str] = []
    for token in text.split():
        probe = cyrillic_to_latin_uz(normalize_apostrophes(token).lower()).strip(_STRIP_CHARS)
        if probe in FILLER_WORDS:
            continue
        kept.append(token)

    if not kept:
        return text
    return " ".join(kept)
