"""LLM domain data models for disambiguation and whole-message parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class DisambiguationCandidateInput:
    """Input candidate SKU sent to LLM for Stage 3 disambiguation."""

    canonical_id: int
    name_uz: str
    brand: str | None = None
    category_name: str | None = None
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DisambiguationResult:
    """Output from Stage 3 LLM candidate disambiguation."""

    canonical_id: int | None
    confidence: float
    reason: str


@dataclass(frozen=True)
class LLMParsedLine:
    """A single line extracted by LLM from an unstructured message."""

    name: str
    qty: Decimal
    unit: str | None
    confidence: float


@dataclass(frozen=True)
class LLMParseResult:
    """Full basket parse result from LLM whole-message fallback."""

    lines: list[LLMParsedLine]
