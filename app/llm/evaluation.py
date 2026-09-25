"""Fail-closed, process-safe reservations for explicitly enabled live tests.

Reservations are never refunded, even after a timeout: the provider may have
billed it. The ledger must be mounted persistently and shared by every test
process. No real call may retry outside this reservation boundary.
"""

import fcntl
import json
import os
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.llm.pricing import CACHE_RATES, RATES


def reserve_agent_evaluation(
    model: str, system: Any, messages: Any, tools: Any, max_output: int
) -> bool:
    path = settings.agent_evaluation_budget_path
    if path is None:
        return True
    rates = RATES.get(model)
    if rates is None or max_output <= 0:
        return False
    # Count serialized UTF-8 bytes rather than optimistic token estimates.
    # Include tool schemas and ample provider framing; charge every input token
    # at cache-write price, never assume a cheaper cache hit.
    content = json.dumps([system, messages, tools], ensure_ascii=False).encode()
    upper_input = len(content) + 8192
    cache_write_price = (
        CACHE_RATES[model][0] if model in CACHE_RATES else rates[0] * Decimal("1.25")
    )
    cost = (cache_write_price * upper_input + rates[1] * max_output) / 1_000_000
    cost = cost.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    limit = min(settings.agent_evaluation_budget_usd, Decimal("5.00"))
    if not limit.is_finite() or limit <= 0:
        return False
    ledger = Path(path)
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.with_suffix(ledger.suffix + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            reserved = Decimal("0")
            if ledger.exists():
                reserved = Decimal(json.loads(ledger.read_text())["reserved_usd"])
            if not reserved.is_finite() or reserved < 0 or reserved + cost > limit:
                return False
            temporary = ledger.with_suffix(ledger.suffix + ".tmp")
            with temporary.open("w") as output:
                json.dump({"reserved_usd": str(reserved + cost), "limit_usd": str(limit)}, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(ledger)
            directory = os.open(ledger.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return True
    except (OSError, ValueError, KeyError, ArithmeticError):
        return False
