from dataclasses import dataclass, field
from typing import Any, Literal

MatchStatus = Literal["auto_accept", "ask_user", "unresolved"]


@dataclass(frozen=True)
class CandidateMatch:
    canonical_id: int
    slug: str
    name_uz: str
    brand: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    search_doc: str = ""
    popularity_hits: int = 0
    is_exact_alias: bool = False
    score: float = 0.0
    match_method: str = "trgm"


@dataclass(frozen=True)
class MatchDecision:
    canonical_id: int | None
    status: MatchStatus
    confidence: float
    candidates: list[CandidateMatch] = field(default_factory=list)
    method: str = "trgm"
    needs_review: bool = False
    # What to put to the customer when the line stays ambiguous -- phrased
    # around the difference that matters (grade, size, colour), not around the
    # catalog name. Empty whenever the match was certain enough to skip asking.
    clarify_question: str | None = None
