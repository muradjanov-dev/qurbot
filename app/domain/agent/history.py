from __future__ import annotations

from decimal import Decimal, InvalidOperation


def trim_history(messages: list[dict[str, str]], max_messages: int) -> list[dict[str, str]]:
    """Keep the latest `max_messages`, starting on a customer message.

    Only plain text turns are remembered between messages; each one is re-sent
    on every call, so the window is what keeps a long chat cheap.
    """
    trimmed = messages[-max_messages:] if max_messages > 0 else []
    while trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]
    return trimmed


def parse_agent_qty(raw: object, max_qty: Decimal) -> Decimal | None:
    """A quantity the model sent, or None if it cannot be ordered. Zero means remove."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        qty = Decimal(str(raw))
    except InvalidOperation:
        return None
    if not qty.is_finite() or qty < 0 or qty > max_qty:
        return None
    return qty
