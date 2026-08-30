"""A long catalogue entry must not be punished for being long.

`search_doc` concatenates the Latin name, the Cyrillic name, the Russian name,
the brand, the size, the grade and the slug. Jaccard similarity divides by the
union, so every extra script in that blob pushed the score down: a query naming
the grade, the thickness and the size of one exact sheet scored 0.47 against
the very row it describes, and landed under the threshold for even asking.

Postgres already knows this -- the candidate search uses `word_similarity`,
which asks how much of the *query* is present, not how alike the two strings
are overall. The in-memory re-ranker has to agree with it, or the two stages
disagree about what a good match is.
"""

from app.domain.matching.trigram import (
    best_match_similarity,
    trigram_containment,
    trigram_similarity,
)

SEARCH_DOC = (
    "fanera berezovaya 3x3 12 mm (1525x1525) "
    "фанера березовая 3х3 12 мм (1525х1525) "
    "фанера березовая 3х3 12 мм (1525х1525) 1525x1525 3x3 "
    "fanera-bereza-3x3-12mm-1525x1525"
)


def test_containment_ignores_the_length_of_the_document() -> None:
    query = "fanera 3x3 12mm 1525x1525"
    assert trigram_containment(query, SEARCH_DOC) > 0.8
    # The symmetric measure is what used to be asked, and this is what it says.
    assert trigram_similarity(query, SEARCH_DOC) < 0.6


def test_containment_still_separates_a_wrong_grade() -> None:
    """Absent trigrams are absent: naming 2x4 against a 3x3 row costs score."""
    right = trigram_containment("fanera 3x3 12mm", SEARCH_DOC)
    wrong = trigram_containment("fanera 2x4 12mm", SEARCH_DOC)
    assert right > wrong


def test_containment_rejects_an_unrelated_query() -> None:
    assert trigram_containment("sement m400", SEARCH_DOC) < 0.4


def test_empty_inputs_score_zero() -> None:
    assert trigram_containment("", SEARCH_DOC) == 0.0
    assert trigram_containment("fanera", "") == 0.0


def test_best_match_uses_whichever_measure_is_kinder() -> None:
    """The single-token path stays -- a one-word query already matched that way."""
    assert best_match_similarity("fanera", "Fanera berezovaya 3x3", SEARCH_DOC) > 0.9
    assert best_match_similarity("fanera 3x3 12mm 1525x1525", None, SEARCH_DOC) > 0.8
