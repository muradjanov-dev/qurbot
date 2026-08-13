import math
from typing import Any

from app.domain.matching.models import CandidateMatch, MatchDecision
from app.domain.matching.trigram import best_match_similarity
from app.domain.models import NormalizedQuery


def compute_attribute_match(query: NormalizedQuery, attributes: dict[str, Any]) -> float:
    """Compute attribute overlap score (e.g. grade, size, diameter)."""
    if not attributes:
        return 0.5 if not query.grades and not query.sizes else 0.0

    score = 0.0
    checks = 0

    # Grade check (e.g. m400)
    attr_grade = attributes.get("grade")
    if attr_grade:
        checks += 1
        grade_clean = str(attr_grade).lower().replace("-", "").replace(" ", "")
        if grade_clean in query.grades or any(g in grade_clean for g in query.grades):
            score += 1.0

    # Diameter check (e.g. 12mm)
    attr_diam = attributes.get("diameter_mm") or attributes.get("thickness_mm")
    if attr_diam:
        checks += 1
        diam_str = f"d{attr_diam}".lower()
        if diam_str in query.grades or any(
            f"{attr_diam}mm" in t or f"d{attr_diam}" in t for t in query.tokens
        ):
            score += 1.0

    # Size check (e.g. 30x30)
    attr_size = attributes.get("size") or attributes.get("dimensions")
    if attr_size:
        checks += 1
        size_clean = str(attr_size).lower().replace(" ", "").replace("*", "x")
        if size_clean in query.sizes or any(s in size_clean for s in query.sizes):
            score += 1.0

    if checks == 0:
        return 0.5

    return score / checks


def compute_brand_match(query: NormalizedQuery, brand: str | None) -> float:
    if not brand:
        return 0.2
    brand_clean = brand.lower().strip()
    if brand_clean in query.text_norm or any(t in brand_clean for t in query.tokens):
        return 1.0
    return 0.0


def compute_popularity_score(popularity_hits: int) -> float:
    if popularity_hits <= 0:
        return 0.0
    return min(1.0, math.log1p(popularity_hits) / math.log1p(100))


def score_and_rank_candidates(
    query: NormalizedQuery,
    candidates: list[CandidateMatch],
    auto_accept_threshold: float = 0.82,
    margin_threshold: float = 0.12,
    ask_user_threshold: float = 0.55,
) -> MatchDecision:
    """Re-rank candidate matches and determine decision status according to SPEC §6."""
    if not candidates:
        return MatchDecision(
            canonical_id=None,
            status="unresolved",
            confidence=0.0,
            candidates=[],
            method="none",
        )

    # Stage 1: Exact alias shortcut
    exact_alias = next((c for c in candidates if c.is_exact_alias), None)
    if exact_alias:
        return MatchDecision(
            canonical_id=exact_alias.canonical_id,
            status="auto_accept",
            confidence=1.0,
            candidates=[exact_alias],
            method="alias",
            needs_review=False,
        )

    # Stage 2: Multi-factor scoring
    scored_candidates: list[CandidateMatch] = []
    for cand in candidates:
        trigram_sim = best_match_similarity(query.text_norm, cand.name_uz, cand.search_doc)
        attr_score = compute_attribute_match(query, cand.attributes)
        brand_score = compute_brand_match(query, cand.brand)
        pop_score = compute_popularity_score(cand.popularity_hits)

        # SPEC §6 formula: 0.45 * trigram + 0.25 * attr + 0.15 * brand + 0.10 * cat + 0.05 * pop
        final_score = (
            0.45 * trigram_sim
            + 0.25 * attr_score
            + 0.15 * brand_score
            + 0.10 * 0.5  # default baseline category prior
            + 0.05 * pop_score
        )

        scored_candidates.append(
            CandidateMatch(
                canonical_id=cand.canonical_id,
                slug=cand.slug,
                name_uz=cand.name_uz,
                brand=cand.brand,
                attributes=cand.attributes,
                search_doc=cand.search_doc,
                popularity_hits=cand.popularity_hits,
                score=round(final_score, 4),
                match_method="trgm",
            )
        )

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x.score, reverse=True)
    top = scored_candidates[0]
    runner_up = scored_candidates[1] if len(scored_candidates) > 1 else None

    margin = (top.score - runner_up.score) if runner_up else 1.0

    # Decision thresholds
    if top.score >= auto_accept_threshold and margin >= margin_threshold:
        return MatchDecision(
            canonical_id=top.canonical_id,
            status="auto_accept",
            confidence=top.score,
            candidates=scored_candidates[:3],
            method="trgm",
            needs_review=False,
        )

    if top.score >= ask_user_threshold:
        return MatchDecision(
            canonical_id=top.canonical_id,
            status="ask_user",
            confidence=top.score,
            candidates=scored_candidates[:3],
            method="trgm",
            needs_review=True,
        )

    return MatchDecision(
        canonical_id=None,
        status="unresolved",
        confidence=top.score,
        candidates=scored_candidates[:3],
        method="trgm",
        needs_review=True,
    )
