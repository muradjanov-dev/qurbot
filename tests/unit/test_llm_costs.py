"""The end-of-day AI bill: how much, on which model, through which API."""

from datetime import UTC, datetime
from decimal import Decimal

from app.domain.llm_costs import (
    ModelSpend,
    format_ai_cost_report,
    llm_provider,
    local_day_start_utc,
)


def test_provider_is_read_from_the_model_name() -> None:
    assert llm_provider("claude-opus-5-5") == "Anthropic"
    assert llm_provider("claude-opus-5") == "Anthropic"
    assert llm_provider("gpt-5.6-terra") == "OpenAI"
    assert llm_provider(None) == "?"
    assert llm_provider("mistral-large") == "?"


def test_report_lists_each_model_and_the_total() -> None:
    text = format_ai_cost_report(
        "14.09.2026",
        [
            ModelSpend(
                "claude-opus-5",
                calls=40,
                input_tokens=120_000,
                output_tokens=9_000,
                cost_usd=Decimal("0.825"),
            ),
            ModelSpend(
                "gpt-5.6-terra",
                calls=10,
                input_tokens=5_000,
                output_tokens=1_000,
                cost_usd=Decimal("0.0225"),
            ),
        ],
    )
    assert "14.09.2026" in text
    assert "Anthropic · claude-opus-5" in text
    assert "OpenAI · gpt-5.6-terra" in text
    assert "$0.83" in text
    assert "$0.85" in text  # total
    # Most expensive first.
    assert text.index("claude-opus-5") < text.index("gpt-5.6-terra")


def test_a_quiet_day_says_so() -> None:
    text = format_ai_cost_report("14.09.2026", [])
    assert "$0.00" in text


def test_tashkent_day_is_measured_in_utc() -> None:
    # 23:55 in Tashkent is 18:55 UTC; the day began at 19:00 UTC the evening before.
    now = datetime(2026, 9, 14, 18, 55, tzinfo=UTC)
    assert local_day_start_utc(now, 5) == datetime(2026, 9, 13, 19, 0, tzinfo=UTC)


def test_just_after_local_midnight_starts_a_new_day() -> None:
    now = datetime(2026, 9, 14, 19, 5, tzinfo=UTC)  # 00:05 on 15.09 in Tashkent
    assert local_day_start_utc(now, 5) == datetime(2026, 9, 14, 19, 0, tzinfo=UTC)
