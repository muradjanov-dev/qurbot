"""Street language has to arrive at the catalog's own wording.

Every fixture below is the shape of message customers actually send: Russian
construction jargon in either script, phonetic spellings, and the politeness
words wrapped around the real request. Matching scores a normalized Latin query
against `search_doc`, which stores the Uzbek Latin name -- so a line that stays
in Russian scores nothing at all. These mappings are what make it comparable,
and they run before any LLM call, which is why they are a dictionary and not a
prompt: free, instant, and identical on every run.
"""

import pytest

from app.domain.normalize.slang import FILLER_WORDS, PRODUCT_SLANG, expand_slang
from app.domain.normalize.text import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Russian trade words, already transliterated by the time slang runs.
        ("kirpich", "g'isht"),
        ("tsement", "sement"),
        ("pesok", "qum"),
        ("shcheben", "shag'al"),
        ("gvozdi", "mix"),
        ("kraska", "bo'yoq"),
        ("kley", "yelim"),
        ("truba", "quvur"),
        ("doska", "taxta"),
        ("provod", "sim"),
        ("uteplitel", "izolyatsiya"),
        # Only the jargon token is touched; quantity and unit survive.
        ("500 dona kirpich", "500 dona g'isht"),
        ("kraska 3 litr", "bo'yoq 3 litr"),
        # Multi-word entries win over the single words inside them.
        ("setka rabitsa", "rabitsa to'r"),
        # A colour names the product as much as the noun does.
        ("krasniy kirpich", "qizil g'isht"),
        ("kraska belaya", "bo'yoq oq"),
        # Word boundaries: a longer word that merely contains a key is left alone.
        ("kirpichniy", "kirpichniy"),
    ],
)
def test_expand_slang(raw: str, expected: str) -> None:
    assert expand_slang(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Cyrillic in, catalog wording out.
        ("кирпич 500 дона", "g'isht 500 dona"),
        ("цемент м400 20 қоп", "sement m400 20 qop"),
        ("щебень 5 тонна", "shag'al 5 tonna"),
        ("песок 2 тонна", "qum 2 tonna"),
        ("трубы 20 дона", "quvur 20 dona"),
        ("красный кирпич 500 дона", "qizil g'isht 500 dona"),
        # Politeness and filler around a real order line.
        ("aka menga 10 qop tsement kere", "10 qop sement"),
        ("iltimos 5 kg gvozdi bervoring", "5 kg mix"),
        ("kraska pochom", "bo'yoq"),
        ("надо 3 куб песок", "3 kub qum"),
        # A line already written in catalog wording must come through untouched.
        ("10 qop sement m400", "10 qop sement m400"),
    ],
)
def test_normalize_text_handles_street_language(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_canonical_wording_is_a_fixed_point() -> None:
    """Expanding an already-canonical term must not rewrite it again.

    A value that is itself a key would rename products on the second pass --
    "kley -> yelim -> something else" -- so the map must terminate in one step.
    """
    for canonical in PRODUCT_SLANG.values():
        assert expand_slang(canonical) == canonical


def test_map_entries_are_normalized_lowercase() -> None:
    for key, value in PRODUCT_SLANG.items():
        assert key == key.lower().strip()
        assert value == value.lower().strip()
        assert key != value, f"{key!r} maps to itself and can be dropped"


def test_filler_words_do_not_shadow_product_words() -> None:
    """A filler word is deleted outright, so it must never name a product."""
    product_words = {word for value in PRODUCT_SLANG.values() for word in value.split()}
    assert FILLER_WORDS.isdisjoint(product_words)
    assert FILLER_WORDS.isdisjoint(PRODUCT_SLANG.keys())


def test_empty_and_whitespace_input() -> None:
    assert expand_slang("") == ""
    assert expand_slang("   ") == "   "
