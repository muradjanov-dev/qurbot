"""Physical constraints checked independently of fuzzy scores and AI confidence."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.models import NormalizedQuery


def attributes_verified(query: NormalizedQuery, attributes: dict[str, Any]) -> bool:
    """Unknown and contradictory attributes both prohibit automatic selection."""
    text = query.raw.lower().replace(",", ".").replace("м", "m")
    # Do not reinterpret metres as millimetres, including zero-padded notation.
    if re.search(r"\d\s*m\b", text):
        return False
    thicknesses = re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*mm\b", text)
    for thickness in thicknesses:
        actual = attributes.get("thickness_mm", attributes.get("diameter_mm"))
        try:
            if actual is None or Decimal(str(actual)) != Decimal(thickness):
                return False
        except InvalidOperation:
            return False
    for grade in query.grades:
        if grade.startswith("d"):
            try:
                if Decimal(str(attributes.get("diameter_mm"))) != Decimal(grade[1:]):
                    return False
            except InvalidOperation:
                return False
        elif str(attributes.get("grade", "")).lower().replace("-", "") != grade:
            return False
    for size in query.sizes:
        if re.fullmatch(r"\dx\d", size):
            if str(attributes.get("grade", "")).replace("/", "x") != size:
                return False
            continue
        actual_size = attributes.get("size", attributes.get("dimensions", ""))
        try:
            expected = [Decimal(p) for p in size.split("x")]
            if all(p < 10 and p != p.to_integral_value() for p in expected):
                expected = [p * 1000 for p in expected]
            actual_parts = re.split(r"[xх×*]", str(actual_size).lower().replace(" ", ""))
            actual = [Decimal(p) for p in actual_parts]
            if sorted(expected) != sorted(actual):
                return False
        except InvalidOperation:
            return False
    return True
