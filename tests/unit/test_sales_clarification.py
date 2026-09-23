"""Broad shopping queries ask for one missing dimension before listing variants."""

import pytest

from app.services.ai_fallback import continue_clarification, missing_spec, product_queries


@pytest.mark.parametrize(
    ("query", "question"),
    [
        ("taxta kerak", "taxta_size"),
        ("fanera va OSB kerak", "fanera_thickness"),
        ("fanera va taxta kerak", "fanera_thickness"),
        ("fanera 12mm va OSB kerak", "fanera_sheet_size"),
        ("OSB kerak", "osb_thickness"),
        ("oq anker kerak", "anker_size"),
        ("taxta 38x168x6000 mm kerak", None),
        ("OSB 12mm kerak", None),
        ("oq anker 10x112 kerak", None),
        ("barcha oq ankerlarni ko'rsat", None),
        ("taxta haqida ma'lumot", None),
    ],
)
def test_missing_spec_is_narrow_and_actionable(query: str, question: str | None) -> None:
    assert missing_spec(query) == question


def test_multi_product_query_splits_after_clarification() -> None:
    assert product_queries("fanera 12 mm 1525x1525 va OSB 9 mm kerak") == [
        "fanera 12 mm 1525x1525",
        "osb 9 mm",
    ]


def test_plain_number_answers_thickness_question() -> None:
    continued = continue_clarification("fanera va osb kerak", "fanera_thickness", "12")
    assert continued is not None
    assert "fanera 12 mm" in continued
    assert missing_spec(continued) == "fanera_sheet_size"
