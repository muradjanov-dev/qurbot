"""Shared parsing for versioned order decision callback payloads."""

from __future__ import annotations


def parse_order_decision_callback(data: str | None, prefix: str) -> tuple[str, int, int]:
    """Parse ``prefix:action:id[:revision]``, treating legacy payloads as revision zero."""
    parts = (data or "").split(":")
    if len(parts) not in {3, 4} or parts[0] != prefix:
        raise ValueError("invalid order decision callback")

    action, raw_id = parts[1], parts[2]
    raw_revision = parts[3] if len(parts) == 4 else "0"
    if (
        not raw_id.isascii()
        or not raw_id.isdigit()
        or not raw_revision.isascii()
        or not raw_revision.isdigit()
    ):
        raise ValueError("invalid order decision callback numbers")

    order_id = int(raw_id)
    workflow_revision = int(raw_revision)
    if order_id <= 0:
        raise ValueError("invalid order id")
    return action, order_id, workflow_revision
