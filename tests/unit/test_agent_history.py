"""The sales agent's memory is short on purpose: every remembered line is paid for again."""

from decimal import Decimal

from app.domain.agent import parse_agent_qty, trim_history


def _turns(n: int) -> list[dict[str, str]]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)]


def test_short_history_is_kept_whole() -> None:
    history = _turns(4)
    assert trim_history(history, max_messages=10) == history


def test_long_history_keeps_only_the_latest_messages() -> None:
    trimmed = trim_history(_turns(10), max_messages=4)
    assert [m["content"] for m in trimmed] == ["m6", "m7", "m8", "m9"]


def test_trimmed_history_always_starts_with_the_customer() -> None:
    """The API refuses a conversation that opens with the assistant."""
    trimmed = trim_history(_turns(10), max_messages=3)
    assert trimmed[0]["role"] == "user"
    assert [m["content"] for m in trimmed] == ["m8", "m9"]


def test_quantity_is_read_as_decimal() -> None:
    assert parse_agent_qty("12.5", max_qty=Decimal(1000)) == Decimal("12.5")
    assert parse_agent_qty(3, max_qty=Decimal(1000)) == Decimal(3)


def test_zero_means_remove() -> None:
    assert parse_agent_qty(0, max_qty=Decimal(1000)) == Decimal(0)


def test_unorderable_quantities_are_refused() -> None:
    for bad in (-1, "abc", None, 5000, "nan", "inf"):
        assert parse_agent_qty(bad, max_qty=Decimal(1000)) is None
