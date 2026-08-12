"""Unit tests for LLM prompt formatting, hash generation, and response parsing."""

import json
from decimal import Decimal

from app.llm.cache import compute_llm_input_hash
from app.llm.models import (
    DisambiguationCandidateInput,
    DisambiguationResult,
    LLMParsedLine,
    LLMParseResult,
)
from app.llm.prompts import (
    format_disambiguation_prompt,
    format_whole_message_prompt,
)


def test_disambiguation_prompt_formatting() -> None:
    candidates = [
        DisambiguationCandidateInput(
            canonical_id=10,
            name_uz="Sement M400",
            brand="Qizilqum",
            attributes={"grade": "M400", "weight_kg": 50},
        ),
        DisambiguationCandidateInput(
            canonical_id=11,
            name_uz="Sement M500",
            brand="Bekobod",
            attributes={"grade": "M500", "weight_kg": 50},
        ),
    ]

    prompt_str = format_disambiguation_prompt(
        raw_query="sement m-400 10 qop",
        normalized_query="sement m400 10 qop",
        candidates=candidates,
    )

    data = json.loads(prompt_str)
    assert data["customer_query"] == "sement m-400 10 qop"
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["id"] == 10
    assert data["candidates"][0]["brand"] == "Qizilqum"


def test_whole_message_prompt_formatting() -> None:
    raw_msg = "menga 10 qop sement, 500 dona gisht va 2 tonna qum kerak"
    prompt_str = format_whole_message_prompt(raw_msg)
    data = json.loads(prompt_str)
    assert data["raw_message"] == raw_msg


def test_llm_input_hash_deterministic() -> None:
    h1 = compute_llm_input_hash("disambiguation", "v1", {"query": "cement", "cand_ids": [1, 2]})
    h2 = compute_llm_input_hash("disambiguation", "v1", {"query": "cement", "cand_ids": [1, 2]})
    h3 = compute_llm_input_hash("disambiguation", "v2", {"query": "cement", "cand_ids": [1, 2]})
    assert h1 == h2
    assert h1 != h3


def test_llm_models_immutability() -> None:
    res = DisambiguationResult(canonical_id=5, confidence=0.92, reason="Match")
    assert res.canonical_id == 5
    assert res.confidence == 0.92

    line = LLMParsedLine(name="Sement", qty=Decimal("10"), unit="qop", confidence=0.95)
    parse_res = LLMParseResult(lines=[line])
    assert len(parse_res.lines) == 1
    assert parse_res.lines[0].qty == Decimal("10")
