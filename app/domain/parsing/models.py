from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ParsedLine:
    line_no: int
    raw_text: str
    parsed_name: str
    qty: Decimal
    unit_code: str | None
    confidence: float = 1.0
    needs_review: bool = False
    user_note: str | None = None
