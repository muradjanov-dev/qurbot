"""Delivery UI formatting that does not depend on the deployment server zone."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_TASHKENT = ZoneInfo("Asia/Tashkent")


def format_delivery_time(value: datetime | None) -> str:
    """Render workflow times in Tashkent time with an explicit zone marker."""
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return f"{value.astimezone(_TASHKENT):%d.%m.%Y %H:%M} UZT"
