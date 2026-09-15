"""The admins' end-of-day AI bill, grouped by model and API provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

_PROVIDER_PREFIXES = (
    ("claude-", "Anthropic"),
    ("gpt-", "OpenAI"),
    ("o1", "OpenAI"),
    ("o3", "OpenAI"),
    ("o4", "OpenAI"),
)
_CENT = Decimal("0.01")
_UNKNOWN_MODEL = "noma'lum"


@dataclass(frozen=True, slots=True)
class ModelSpend:
    model: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


def llm_provider(model: str | None) -> str:
    """Which API a model is billed through, from its name. '?' when unknown."""
    name = (model or "").lower()
    for prefix, provider in _PROVIDER_PREFIXES:
        if name.startswith(prefix):
            return provider
    return "?"


def _usd(value: Decimal) -> str:
    return f"${value.quantize(_CENT, rounding=ROUND_HALF_UP)}"


def format_ai_cost_report(day_label: str, rows: list[ModelSpend]) -> str:
    total = sum((row.cost_usd for row in rows), Decimal(0))
    lines = [f"🤖 <b>AI xarajati — {day_label}</b>", f"Jami: <b>{_usd(total)}</b>"]
    for row in sorted(rows, key=lambda r: r.cost_usd, reverse=True):
        lines.append(
            f"\n• {llm_provider(row.model)} · {row.model or _UNKNOWN_MODEL}\n"
            f"   {_usd(row.cost_usd)} — {row.calls} so'rov, "
            f"{row.input_tokens:,} kirish / {row.output_tokens:,} chiqish token"
        )
    return "\n".join(lines)


def local_day_start_utc(now: datetime, utc_offset_hours: int) -> datetime:
    """Midnight of the local (e.g. Tashkent) day containing `now`, expressed in UTC."""
    local = now + timedelta(hours=utc_offset_hours)
    midnight = datetime(local.year, local.month, local.day, tzinfo=UTC)
    return midnight - timedelta(hours=utc_offset_hours)
