import re

# Apostrophe characters commonly typed on Uzbek/Russian keyboards
APOSTROPHE_REGEX = re.compile(r"[ʻʼ‘’`´\u02BB\u02BC\u2018\u2019\u0060\u00B4]")


def normalize_apostrophes(text: str) -> str:
    """Normalize all non-standard apostrophe glyphs to standard ASCII single quote '."""
    return APOSTROPHE_REGEX.sub("'", text)


# Cyrillic to Latin mapping for Uzbek
UZ_CYRL_TO_LATN_MULTI = [
    ("ў", "o'"),
    ("Ў", "O'"),
    ("ғ", "g'"),
    ("Ғ", "G'"),
    ("ш", "sh"),
    ("Ш", "Sh"),
    ("ч", "ch"),
    ("Ч", "Ch"),
    ("я", "ya"),
    ("Я", "Ya"),
    ("ю", "yu"),
    ("Ю", "Yu"),
    ("ё", "yo"),
    ("Ё", "Yo"),
    ("ц", "ts"),
    ("Ц", "Ts"),
    # Not part of the Uzbek Cyrillic alphabet, but constant in the Russian
    # words customers mix in -- "щебень", "трубы". Left unmapped, those tokens
    # stayed Cyrillic and matched nothing at all.
    ("щ", "shch"),
    ("Щ", "Shch"),
]

UZ_CYRL_TO_LATN_SINGLE = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ҳ": "h",
    "қ": "q",
    "ы": "y",
    "э": "e",
    "ъ": "'",
    "ь": "",
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Е": "E",
    "Ж": "J",
    "З": "Z",
    "И": "I",
    "Й": "Y",
    "К": "K",
    "Л": "L",
    "М": "M",
    "Н": "N",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "У": "U",
    "Ф": "F",
    "Х": "X",
    "Ҳ": "H",
    "Қ": "Q",
    "Ы": "Y",
    "Э": "E",
    "Ъ": "'",
    "Ь": "",
}

# Latin to Cyrillic mapping for Uzbek
UZ_LATN_TO_CYRL_MULTI = [
    ("o'", "ў"),
    ("O'", "Ў"),
    ("g'", "ғ"),
    ("G'", "Ғ"),
    ("sh", "ш"),
    ("Sh", "Ш"),
    ("SH", "Ш"),
    ("ch", "ч"),
    ("Ch", "Ч"),
    ("CH", "Ч"),
    ("ya", "я"),
    ("Ya", "Я"),
    ("YA", "Я"),
    ("yu", "ю"),
    ("Yu", "Ю"),
    ("YU", "Ю"),
    ("yo", "ё"),
    ("Yo", "Ё"),
    ("YO", "Ё"),
    ("ts", "ц"),
    ("Ts", "Ц"),
    ("TS", "Ц"),
]

UZ_LATN_TO_CYRL_SINGLE = {
    "a": "а",
    "b": "б",
    "v": "в",
    "g": "г",
    "d": "д",
    "e": "е",
    "j": "ж",
    "z": "з",
    "i": "и",
    "y": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "f": "ф",
    "x": "х",
    "h": "ҳ",
    "q": "қ",
    "A": "А",
    "B": "Б",
    "V": "В",
    "G": "Г",
    "D": "Д",
    "E": "Е",
    "J": "Ж",
    "Z": "З",
    "I": "И",
    "Y": "Й",
    "K": "К",
    "L": "Л",
    "M": "М",
    "N": "Н",
    "O": "О",
    "P": "П",
    "R": "Р",
    "S": "С",
    "T": "Т",
    "U": "У",
    "F": "Ф",
    "X": "Х",
    "H": "Ҳ",
    "Q": "Қ",
    "'": "ъ",
}

RU_CYRL_TO_LATN_MULTI = [
    ("щ", "shch"),
    ("Щ", "Shch"),
    ("ш", "sh"),
    ("Ш", "Sh"),
    ("ч", "ch"),
    ("Ч", "Ch"),
    ("ж", "zh"),
    ("Ж", "Zh"),
    ("я", "ya"),
    ("Я", "Ya"),
    ("ю", "yu"),
    ("Ю", "Yu"),
    ("ё", "yo"),
    ("Ё", "Yo"),
    ("э", "e"),
    ("Э", "E"),
    ("ц", "ts"),
    ("Ц", "Ts"),
    # Not part of the Uzbek Cyrillic alphabet, but constant in the Russian
    # words customers mix in -- "щебень", "трубы". Left unmapped, those tokens
    # stayed Cyrillic and matched nothing at all.
    ("щ", "shch"),
    ("Щ", "Shch"),
]

RU_CYRL_TO_LATN_SINGLE = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ы": "y",
    "ъ": "",
    "ь": "",
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Е": "E",
    "З": "Z",
    "И": "I",
    "Й": "Y",
    "К": "K",
    "Л": "L",
    "М": "M",
    "Н": "N",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "У": "U",
    "Ф": "F",
    "Х": "Kh",
    "Ы": "Y",
    "Ъ": "",
    "Ь": "",
}


def cyrillic_to_latin_uz(text: str) -> str:
    """Transliterate Uzbek Cyrillic text to Uzbek Latin."""
    out = text
    for cyrl, lat in UZ_CYRL_TO_LATN_MULTI:
        out = out.replace(cyrl, lat)
    return "".join(UZ_CYRL_TO_LATN_SINGLE.get(ch, ch) for ch in out)


def latin_to_cyrillic_uz(text: str) -> str:
    """Transliterate Uzbek Latin text to Uzbek Cyrillic."""
    out = normalize_apostrophes(text)
    for lat, cyrl in UZ_LATN_TO_CYRL_MULTI:
        out = out.replace(lat, cyrl)
    return "".join(UZ_LATN_TO_CYRL_SINGLE.get(ch, ch) for ch in out)


def transliterate_ru_to_lat(text: str) -> str:
    """Transliterate Russian Cyrillic text to standard Latin representation."""
    out = text
    for cyrl, lat in RU_CYRL_TO_LATN_MULTI:
        out = out.replace(cyrl, lat)
    return "".join(RU_CYRL_TO_LATN_SINGLE.get(ch, ch) for ch in out)
