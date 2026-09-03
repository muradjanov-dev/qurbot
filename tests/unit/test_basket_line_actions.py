"""Every product in the basket can be changed on its own.

The basket offered exactly two tools: rewrite the whole list, or delete all of
it. Fixing the third of three items meant retyping the other two -- which is
the moment an older customer gives up and calls instead.
"""

from app.bot.keyboards.inline import MAX_PER_LINE_ROWS, get_basket_actions_keyboard


def _callbacks(markup: object) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]  # type: ignore[attr-defined]


def test_each_line_gets_its_own_change_and_remove() -> None:
    markup = get_basket_actions_keyboard(lang="uz_latn", line_numbers=[1, 2, 3])
    callbacks = _callbacks(markup)

    for line_no in (1, 2, 3):
        assert f"line_edit:{line_no}" in callbacks
        assert f"line_del:{line_no}" in callbacks


def test_the_buttons_carry_the_line_number_the_table_shows() -> None:
    """The customer is matching "2." to "2.", not reading labels."""
    markup = get_basket_actions_keyboard(lang="uz_latn", line_numbers=[2])
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert any(text.startswith("2.") for text in texts)


def test_the_whole_basket_actions_are_still_there() -> None:
    callbacks = _callbacks(get_basket_actions_keyboard(lang="uz_latn", line_numbers=[1]))
    for expected in ("add_item", "clear_basket", "back_to_menu", "calculate_quotes"):
        assert expected in callbacks


def test_ordering_stays_the_last_button() -> None:
    markup = get_basket_actions_keyboard(lang="uz_latn", line_numbers=[1, 2])
    last_row = markup.inline_keyboard[-1]
    assert last_row[0].callback_data == "calculate_quotes"
    assert last_row[0].text.startswith("✅")


def test_a_long_basket_does_not_bury_the_order_button() -> None:
    """Past a screenful, per-line rows would push the order button out of reach."""
    markup = get_basket_actions_keyboard(lang="uz_latn", line_numbers=list(range(1, 21)))
    callbacks = _callbacks(markup)

    assert callbacks.count("calculate_quotes") == 1
    assert len([c for c in callbacks if c.startswith("line_edit:")]) == MAX_PER_LINE_ROWS


def test_no_lines_means_no_per_line_rows() -> None:
    callbacks = _callbacks(get_basket_actions_keyboard(lang="uz_latn"))
    assert not any(c.startswith("line_") for c in callbacks)
