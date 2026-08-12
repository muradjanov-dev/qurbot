from decimal import Decimal

import pytest

from app.domain.normalize.text import (
    extract_grades,
    extract_numbers,
    extract_sizes,
    extract_stopwords,
    normalize_query,
    normalize_text,
    unify_unit_str,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  10  QOP   Sement  M-400  ", "10 qop sement m400"),
        ("цемент м400 - 20 қоп", "sement m400 20 qop"),
        ("армaтура 12мм 500 кг", "armatura 12mm 500 kg"),
        ("30 х 30 kafel", "30x30 kafel"),
        ("Ø12 armatura", "d12 armatura"),
        ("500 dona g'isht sifatli original", "500 dona g'isht"),
        ("50 dona shipr", "50 dona shifer"),
        ("шипр", "shifer"),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    norm = normalize_text(raw)
    assert norm == expected


@pytest.mark.parametrize(
    ("unit_in", "expected_code"),
    [
        ("кг", "kg"),
        ("kg", "kg"),
        ("kilo", "kg"),
        ("kilogramm", "kg"),
        ("дона", "dona"),
        ("dona", "dona"),
        ("шт", "dona"),
        ("sht", "dona"),
        ("pcs", "dona"),
        ("қоп", "qop"),
        ("qop", "qop"),
        ("мешок", "qop"),
        ("meshok", "qop"),
        ("м2", "m2"),
        ("m2", "m2"),
        ("m²", "m2"),
        ("kv.m", "m2"),
        ("кв.м", "m2"),
        ("м3", "m3"),
        ("kub", "m3"),
        ("m3", "m3"),
        ("литр", "litr"),
        ("l", "litr"),
        ("litr", "litr"),
    ],
)
def test_unify_unit_str(unit_in: str, expected_code: str) -> None:
    assert unify_unit_str(unit_in) == expected_code


def test_extract_grades() -> None:
    text = "sement m400 va beton m-350 hamda a500c"
    grades = extract_grades(text)
    assert "m400" in grades
    assert "m350" in grades
    assert "a500c" in grades


def test_extract_sizes() -> None:
    text = "plitka 30x30 va brus 50*50 hamda 600х300х200"
    sizes = extract_sizes(text)
    assert "30x30" in sizes
    assert "50x50" in sizes
    assert "600x300x200" in sizes


def test_extract_numbers() -> None:
    text = "10 qop sement, 12.5 metr va 500 dona"
    numbers = extract_numbers(text)
    assert Decimal("10") in numbers
    assert Decimal("12.5") in numbers
    assert Decimal("500") in numbers


def test_extract_stopwords() -> None:
    text = "sement sifatli original arzon aksiya va yangi"
    clean, stopwords = extract_stopwords(text)
    assert "sifatli" in stopwords
    assert "original" in stopwords
    assert "aksiya" in stopwords
    assert "sement" in clean


def test_normalize_empty_text() -> None:
    assert normalize_text("") == ""
    assert normalize_text("   ") == ""


def test_normalize_query_object() -> None:
    raw = "10 qop sement m 400 sifatli"
    nq = normalize_query(raw)
    assert nq.raw == raw
    assert "sement" in nq.tokens
    assert "m400" in nq.grades
    assert "qop" in nq.units
    assert Decimal("10") in nq.numbers
    assert "sifatli" in nq.stopwords


def test_extract_d_grades() -> None:
    grades = extract_grades("armatura d14 va D 16 hamda Ø 18")
    assert "d14" in grades
    assert "d16" in grades
    assert "d18" in grades
