"""What the customer did not say must not count against a product.

A buyer who writes "10 dona fanera" has named the product and left the size,
grade and thickness to the shop -- which is exactly how this trade is spoken.
Scoring treated every attribute the candidate carried as a failed check, so a
bare family word landed at 0.53, under the 0.55 needed to even ask, and the
customer was told the catalog has no fanera while the catalog held thirty.

An attribute the customer *did* state and got wrong is still a mismatch: a
grade is not a near miss, it is a different sheet at a different price.
"""

from app.domain.matching.models import CandidateMatch
from app.domain.matching.scorer import compute_attribute_match, score_and_rank_candidates
from app.domain.normalize.text import normalize_query

PLYWOOD_ATTRS = {"grade": "3x3", "size": "1525x1525", "thickness_mm": 12}


def _candidate(name: str, attrs: dict[str, object] | None = None) -> CandidateMatch:
    return CandidateMatch(
        canonical_id=abs(hash(name)) % 10000,
        slug=name.lower().replace(" ", "-"),
        name_uz=name,
        brand=None,
        attributes=dict(attrs if attrs is not None else PLYWOOD_ATTRS),
        search_doc=name.lower(),
    )


def test_unspecified_attributes_are_neutral() -> None:
    """ "fanera" says nothing about grade, size or thickness -- so neither counts."""
    assert compute_attribute_match(normalize_query("fanera"), PLYWOOD_ATTRS) == 0.5


def test_a_stated_attribute_still_has_to_agree() -> None:
    matching = compute_attribute_match(normalize_query("fanera 3x3"), PLYWOOD_ATTRS)
    mismatching = compute_attribute_match(normalize_query("fanera 2x4"), PLYWOOD_ATTRS)
    assert matching > mismatching
    assert mismatching == 0.0


def test_only_the_stated_attribute_is_scored() -> None:
    """A right size must not be dragged down by a grade nobody mentioned."""
    assert compute_attribute_match(normalize_query("fanera 1525x1525"), PLYWOOD_ATTRS) == 1.0


def test_bare_family_word_asks_instead_of_giving_up() -> None:
    """The bug from the shop floor: "10 dona fanera" answered "topilmadi"."""
    candidates = [
        _candidate("Fanera berezovaya 3x3 12 mm (1525x1525)"),
        _candidate(
            "Fanera berezovaya 2x4 9 mm (2440x1220)",
            {"grade": "2x4", "size": "2440x1220", "thickness_mm": 9},
        ),
        _candidate(
            "Fanera laminatsiyalangan 18 mm (2440x1220)",
            {"size": "2440x1220", "thickness_mm": 18, "material": "laminated_plywood"},
        ),
    ]

    decision = score_and_rank_candidates(
        query=normalize_query("fanera"),
        candidates=candidates,
        auto_accept_threshold=0.82,
        margin_threshold=0.12,
        ask_user_threshold=0.55,
    )

    assert decision.status == "ask_user", f"scored {decision.confidence}"
    assert decision.candidates, "the customer needs something to choose between"


def test_a_named_sheet_still_auto_accepts() -> None:
    """Naming grade, thickness and size must stay decisive, not merely neutral."""
    candidates = [
        _candidate("Fanera berezovaya 3x3 12 mm (1525x1525)"),
        _candidate(
            "Fanera berezovaya 2x4 9 mm (2440x1220)",
            {"grade": "2x4", "size": "2440x1220", "thickness_mm": 9},
        ),
    ]
    decision = score_and_rank_candidates(
        query=normalize_query("fanera 3x3 12mm 1525x1525"),
        candidates=candidates,
        auto_accept_threshold=0.82,
        margin_threshold=0.12,
        ask_user_threshold=0.55,
    )
    assert decision.canonical_id == candidates[0].canonical_id
    assert decision.status in ("auto_accept", "ask_user")
    assert decision.confidence > 0.55
