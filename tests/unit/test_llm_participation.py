"""Which lines the AI is asked about.

Deterministic search is fast, free and repeatable, so it goes first and keeps
whatever it is certain of. Everything it is *not* certain of is where accuracy
is actually lost -- a line scored 0.6 is a coin the search is not qualified to
flip -- so the model sees all of it, in the one batched call the basket already
pays for.

What it never sees: a line an approved alias matched exactly, and a line with
no candidates at all. The first is already certain and free; the second gives
the model nothing to choose between.
"""

from decimal import Decimal

from app.domain.matching.models import CandidateMatch, MatchDecision, MatchStatus
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.services.catalog_service import CatalogService, _DeterministicMatch

CANDIDATE = CandidateMatch(
    canonical_id=1,
    slug="fanera-bereza-3x3-12mm-1525x1525",
    name_uz="Fanera berezovaya 3x3 12 mm (1525x1525)",
    attributes={"grade": "3x3", "size": "1525x1525", "thickness_mm": 12},
    search_doc="fanera berezovaya 3x3 12 mm (1525x1525)",
)


def _match(
    status: MatchStatus,
    confidence: float,
    *,
    method: str = "trgm",
    candidates: list[CandidateMatch] | None = None,
) -> _DeterministicMatch:
    line = ParsedLine(
        line_no=1,
        raw_text="10 dona fanera",
        parsed_name="fanera",
        qty=Decimal("10"),
        unit_code="dona",
    )
    cands = CANDIDATE if candidates is None else None
    resolved = [CANDIDATE] if candidates is None else candidates
    assert cands is not None or candidates is not None
    return _DeterministicMatch(
        parsed_line=line,
        query=normalize_query("fanera"),
        decision=MatchDecision(
            canonical_id=CANDIDATE.canonical_id if status != "unresolved" else None,
            status=status,
            confidence=confidence,
            candidates=resolved,
            method=method,
        ),
        candidates=resolved,
    )


def test_an_uncertain_line_goes_to_the_model() -> None:
    """The band between "ask the customer" and "certain" is where accuracy is won."""
    assert CatalogService._needs_llm(_match("ask_user", 0.66)) is True


def test_an_unresolved_line_goes_to_the_model() -> None:
    assert CatalogService._needs_llm(_match("unresolved", 0.31)) is True


def test_a_confident_match_is_left_alone() -> None:
    assert CatalogService._needs_llm(_match("auto_accept", 0.91)) is False


def test_an_exact_alias_is_never_second_guessed() -> None:
    """Stage 1 is an exact hit on an approved alias: certain, and free."""
    assert CatalogService._needs_llm(_match("auto_accept", 1.0, method="alias")) is False


def test_a_line_with_no_candidates_goes_too_and_matters_most() -> None:
    """This is the "katalogda topilmadi" the customer actually sees.

    With nothing to choose from the model cannot pick an id, but it can say
    what the line means -- and the search is then run again on that wording,
    which is how a product the catalog carries under another name is found.
    """
    assert CatalogService._needs_llm(_match("unresolved", 0.0, candidates=[])) is True
