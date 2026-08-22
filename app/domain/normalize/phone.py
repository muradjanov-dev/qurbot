"""Uzbek phone number normalisation.

Pure: no I/O, no clock. The bot needs one canonical form for a contact number
because a shop is handed it to call the customer back -- "90 123 45 67" and
"+998901234567" have to reach the same place.
"""

from __future__ import annotations

# Uzbek subscriber numbers are 9 digits after the 998 country code, and the
# operator code (the first two) always starts with one of these. Checking the
# leading digit rather than an explicit list of codes leaves room for operators
# to be allocated new ones without this rejecting real customers.
_OPERATOR_LEADING_DIGITS = frozenset("356789")

_NATIONAL_LENGTH = 9
_COUNTRY_CODE = "998"

# Characters people put in a phone number that carry no information.
_SEPARATORS = str.maketrans("", "", " -() .")


def normalize_uz_phone(raw: str) -> str | None:
    """Return the number as ``+998XXXXXXXXX``, or None if it is not one.

    Accepts the national 9-digit form, the 998-prefixed form, and either with
    a leading ``+`` or the punctuation people type between the groups.
    """
    if not raw:
        return None

    cleaned = raw.strip().translate(_SEPARATORS)
    cleaned = cleaned.removeprefix("+")

    if not cleaned.isdigit():
        return None

    national = cleaned[len(_COUNTRY_CODE) :] if cleaned.startswith(_COUNTRY_CODE) else cleaned

    if len(national) != _NATIONAL_LENGTH:
        return None
    if national[0] not in _OPERATOR_LEADING_DIGITS:
        return None

    return f"+{_COUNTRY_CODE}{national}"
