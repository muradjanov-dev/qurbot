from datetime import UTC, datetime

from app.core.delivery_format import format_delivery_time


def test_workflow_timestamps_are_rendered_in_tashkent_time() -> None:
    assert format_delivery_time(datetime(2026, 9, 29, 12, 15, tzinfo=UTC)) == (
        "29.09.2026 17:15 UZT"
    )


def test_legacy_naive_timestamp_is_treated_as_utc() -> None:
    assert format_delivery_time(datetime(2026, 9, 29, 12, 15)) == "29.09.2026 17:15 UZT"
