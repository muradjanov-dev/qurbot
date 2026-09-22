import pytest

from app.domain.normalize.translit import (
    cyrillic_to_latin_uz,
    latin_to_cyrillic_uz,
    normalize_apostrophes,
    transliterate_ru_to_lat,
)


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("g‘isht", "g'isht"),
        ("gʼisht", "g'isht"),
        ("gʻisht", "g'isht"),
        ("g’isht", "g'isht"),
        ("g`isht", "g'isht"),
        ("o‘roq", "o'roq"),
        ("bog‘lash", "bog'lash"),
    ],
)
def test_normalize_apostrophes(input_text: str, expected: str) -> None:
    assert normalize_apostrophes(input_text) == expected


@pytest.mark.parametrize(
    ("cyrl_text", "expected_latin"),
    [
        ("ғишт", "g'isht"),
        ("цемент", "tsement"),
        ("қоришма", "qorishma"),
        ("ўроқ", "o'roq"),
        ("шағал", "shag'al"),
        ("арматура", "armatura"),
        ("ёғоч", "yog'och"),
        ("бўёқ", "bo'yoq"),
        ("ғишт м100", "g'isht m100"),
        ("қоп", "qop"),
        ("ҳажм", "hajm"),
        ("электр", "elektr"),
    ],
)
def test_cyrillic_to_latin_uz(cyrl_text: str, expected_latin: str) -> None:
    result = cyrillic_to_latin_uz(cyrl_text)
    assert normalize_apostrophes(result.lower()) == expected_latin


def test_transliterate_ru_to_lat() -> None:
    assert transliterate_ru_to_lat("кирпич") == "kirpich"
    assert transliterate_ru_to_lat("краска") == "kraska"
    assert transliterate_ru_to_lat("штукатурка") == "shtukaturka"
    assert transliterate_ru_to_lat("клей для плитки") == "kley dlya plitki"


def test_roundtrip_uz() -> None:
    words = ["armatura", "sement", "shag'al", "bo'yoq", "yog'och", "penoblok", "qum"]
    for w in words:
        cyrl = latin_to_cyrillic_uz(w)
        lat = normalize_apostrophes(cyrillic_to_latin_uz(cyrl))
        assert lat == w


def test_word_initial_e_and_ye_uz() -> None:
    """Uzbek Cyrillic spells /e/ and /ye/ by position, not by letter.

    A word starting with "e" takes э ("emas" -> "эмас"); a word starting with
    "ye" takes е ("yer" -> "ер"). Mapping the letters independently produced
    "емас" and "йер", which is what a Cyrillic reader saw in the waiting
    messages and in every transliterated district name.
    """
    assert latin_to_cyrillic_uz("emas") == "эмас"
    assert latin_to_cyrillic_uz("eng") == "энг"
    assert latin_to_cyrillic_uz("Eshik") == "Эшик"
    assert latin_to_cyrillic_uz("yer") == "ер"
    assert latin_to_cyrillic_uz("yetkazish") == "етказиш"
    assert latin_to_cyrillic_uz("Yetti") == "Етти"
    # Mid-word the plain е is correct in both cases.
    assert latin_to_cyrillic_uz("kel") == "кел"
    assert latin_to_cyrillic_uz("sement") == "семент"
    assert latin_to_cyrillic_uz("shart emas") == "шарт эмас"
    assert latin_to_cyrillic_uz("eng qulay yer") == "энг қулай ер"
