"""List-price estimates, not invoices. Verified 2026-09-14.

https://developers.openai.com/api/docs/models/gpt-5.6-luna
https://developers.openai.com/api/docs/models/gpt-5.6-terra
https://platform.claude.com/docs/en/models/overview
Custom providers may charge differently and require explicit rates.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

RATES = {
    "gpt-5.6-luna": (Decimal("0.20"), Decimal("1.20")),
    "gpt-5.6-terra": (Decimal("2.00"), Decimal("12.00")),
    "claude-opus-5": (Decimal("5.00"), Decimal("25.00")),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    rates = RATES.get(model)
    if rates is None:
        return None
    return ((rates[0] * input_tokens + rates[1] * output_tokens) / 1_000_000).quantize(
        Decimal("0.000001")
    )


@dataclass
class EvaluationBudget:
    """Reserve the worst-case charge before every attempt, including retries.

    Failed calls retain their reservation: a timeout may still be billed.
    UTF-8 bytes plus generous framing overhead bound text input tokens.
    """

    limit: Decimal = Decimal("2.00")
    reserved: Decimal = Decimal("0")
    ledger_path: Path | None = None

    def __post_init__(self) -> None:
        if self.ledger_path and self.ledger_path.exists():
            previous = Decimal(json.loads(self.ledger_path.read_text())["reserved_usd"])
            self.reserved = max(self.reserved, previous)

    def reserve(self, model: str, system: str, user: str, max_output: int) -> bool:
        upper_input = len(system.encode()) + len(user.encode()) + 1024
        cost = estimate_cost(model, upper_input, max_output)
        if cost is None or self.reserved + cost > self.limit:
            return False
        self.reserved += cost
        if self.ledger_path is not None:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.ledger_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"reserved_usd": str(self.reserved)}))
            temporary.replace(self.ledger_path)
        return True
