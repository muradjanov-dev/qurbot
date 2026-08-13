from app.domain.matching.models import CandidateMatch
from app.domain.matching.scorer import score_and_rank_candidates
from app.domain.matching.trigram import trigram_similarity
from app.domain.models import NormalizedQuery


def test_trigram_similarity() -> None:
    # Exact
    assert trigram_similarity("sement m400", "sement m400") == 1.0

    # High similarity
    sim1 = trigram_similarity("sement m400", "qizilqum sement m400")
    assert sim1 >= 0.5

    # Low similarity
    sim2 = trigram_similarity("gisht m100", "armatura 12mm")
    assert sim2 < 0.2


def test_score_exact_alias() -> None:
    query = NormalizedQuery(
        raw="sement m400",
        text_norm="sement m400",
        tokens=["sement", "m400"],
        grades=["m400"],
    )
    candidates = [
        CandidateMatch(
            canonical_id=1,
            slug="qizilqum-sement-m400-50kg",
            name_uz="Qizilqum Sement M400 (50 kg)",
            brand="Qizilqumsement",
            attributes={"grade": "M400"},
            search_doc="qizilqum sement m400 50kg",
            is_exact_alias=True,
        )
    ]

    decision = score_and_rank_candidates(query, candidates)
    assert decision.status == "auto_accept"
    assert decision.canonical_id == 1
    assert decision.confidence == 1.0
    assert decision.method == "alias"


def test_score_auto_accept_with_trigram_and_attributes() -> None:
    query = NormalizedQuery(
        raw="qizilqum sement m400",
        text_norm="qizilqum sement m400",
        tokens=["qizilqum", "sement", "m400"],
        grades=["m400"],
    )
    candidates = [
        CandidateMatch(
            canonical_id=1,
            slug="qizilqum-sement-m400-50kg",
            name_uz="Qizilqum Sement M400 (50 kg)",
            brand="Qizilqumsement",
            attributes={"grade": "M400"},
            search_doc="qizilqum sement m400 50kg",
            popularity_hits=10,
        ),
        CandidateMatch(
            canonical_id=2,
            slug="bekobod-sement-m400-50kg",
            name_uz="Bekobod Sement M400 (50 kg)",
            brand="Bekobodcement",
            attributes={"grade": "M400"},
            search_doc="bekobod sement m400 50kg",
            popularity_hits=2,
        ),
    ]

    decision = score_and_rank_candidates(query, candidates)
    assert decision.status == "auto_accept"
    assert decision.canonical_id == 1
    assert decision.confidence >= 0.82
    assert decision.method == "trgm"


def test_score_ask_user_when_ambiguous() -> None:
    # Ambiguous query with 2 very close options
    query = NormalizedQuery(
        raw="sement m400",
        text_norm="sement m400",
        tokens=["sement", "m400"],
        grades=["m400"],
    )
    candidates = [
        CandidateMatch(
            canonical_id=1,
            slug="qizilqum-sement-m400-50kg",
            name_uz="Qizilqum Sement M400 (50 kg)",
            brand="Qizilqumsement",
            attributes={"grade": "M400"},
            search_doc="qizilqum sement m400 50kg",
        ),
        CandidateMatch(
            canonical_id=2,
            slug="bekobod-sement-m400-50kg",
            name_uz="Bekobod Sement M400 (50 kg)",
            brand="Bekobodcement",
            attributes={"grade": "M400"},
            search_doc="bekobod sement m400 50kg",
        ),
    ]

    # Without high margin over runner up, falls to ask_user
    decision = score_and_rank_candidates(query, candidates, auto_accept_threshold=0.90)
    assert decision.status == "ask_user"
    assert len(decision.candidates) >= 2


def test_score_short_query_against_bloated_multiscript_search_doc() -> None:
    # Real seed data concatenates several scripts/aliases into one long search_doc
    # (see scripts/seed.py), which used to dilute whole-string trigram similarity
    # for short single-word queries even when the word is an exact token match.
    query = NormalizedQuery(
        raw="sement",
        text_norm="sement",
        tokens=["sement"],
    )
    candidates = [
        CandidateMatch(
            canonical_id=1,
            slug="qizilqum-sement-m400-50kg",
            name_uz="Qizilqum Sement M400 (50 kg)",
            brand="Qizilqumsement",
            attributes={"grade": "M400"},
            search_doc=(
                "qizilqum sement m400 (50 kg) қизилқум "
                "цемент м400 (50 кг) "
                "цемент кызылкум "
                "м400 (50 кг) qizilqumsement qizilqum-sement-m400-50kg"
            ),
        )
    ]

    decision = score_and_rank_candidates(query, candidates)
    assert decision.status in ("auto_accept", "ask_user")
    assert decision.canonical_id == 1


def test_score_unresolved_when_low() -> None:
    query = NormalizedQuery(
        raw="kosmik kema",
        text_norm="kosmik kema",
        tokens=["kosmik", "kema"],
    )
    candidates = [
        CandidateMatch(
            canonical_id=1,
            slug="qizilqum-sement-m400-50kg",
            name_uz="Qizilqum Sement M400 (50 kg)",
            brand="Qizilqumsement",
            attributes={"grade": "M400"},
            search_doc="qizilqum sement m400 50kg",
        )
    ]

    decision = score_and_rank_candidates(query, candidates)
    assert decision.status == "unresolved"
    assert decision.canonical_id is None
