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


@dataclass(frozen=True)
class BatchLineInput:
    """One unresolved basket line, as handed to the batched disambiguation call."""

    line_no: int
    raw_text: str
    normalized_text: str
    candidates: list[DisambiguationCandidateInput] = field(default_factory=list)


@dataclass(frozen=True)
class BatchLineDecision:
    """The model's answer for a single line of a batch.

    `question` is what to ask the customer when the model stayed torn between
    plausible candidates -- the deciding detail, in the customer's language.
    """

    line_no: int
    canonical_id: int | None
    confidence: float
    reason: str = ""
    question: str | None = None


@dataclass(frozen=True)
class BatchDisambiguationResult:
    """Answers keyed by the line_no they were asked about.

    A line the model skipped is simply absent: the caller keeps the
    deterministic decision it already had rather than inventing one.
    """

    lines: dict[int, BatchLineDecision] = field(default_factory=dict)
