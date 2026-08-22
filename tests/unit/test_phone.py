"""Uzbek phone number normalisation.

The checkout used to take whatever text arrived as the contact number, so the
placeholder from the prompt itself -- "+998XXXXXXXXX" -- was stored on a real
order, leaving nobody to call about it.
"""

from app.domain.normalize.phone import normalize_uz_phone


def test_accepts_full_international_form() -> None:
    assert normalize_uz_phone("+998901234567") == "+998901234567"


def test_accepts_national_nine_digits() -> None:
    assert normalize_uz_phone("901234567") == "+998901234567"


def test_accepts_human_formatting() -> None:
    """People type the number the way it is printed on a business card."""
    assert normalize_uz_phone("+998 (90) 123-45-67") == "+998901234567"
    assert normalize_uz_phone("998 90 123 45 67") == "+998901234567"


def test_rejects_the_prompt_placeholder() -> None:
    """The exact string the bot shows as an example is not a phone number."""
    assert normalize_uz_phone("+998XXXXXXXXX") is None
    assert normalize_uz_phone("+998xxxxxxxxx") is None


def test_rejects_wrong_length() -> None:
    assert normalize_uz_phone("+99890123456") is None
    assert normalize_uz_phone("+9989012345678") is None
    assert normalize_uz_phone("") is None


def test_rejects_unknown_operator_code() -> None:
    """A 9-digit number starting 0/1/2/4 is not an Uzbek subscriber number."""
    assert normalize_uz_phone("012345678") is None
    assert normalize_uz_phone("+998112345678") is None


def test_rejects_letters_mixed_in() -> None:
    assert normalize_uz_phone("+99890123O567") is None
    assert normalize_uz_phone("telefonim yoq") is None
