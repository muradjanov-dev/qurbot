"""Unit tests for LLM prompt formatting, hash generation, and response parsing."""

import json
from decimal import Decimal

from app.llm.cache import compute_llm_input_hash
from app.llm.client import LLMClient
from app.llm.models import (
    BatchLineInput,
    DisambiguationCandidateInput,
    DisambiguationResult,
    LLMParsedLine,
    LLMParseResult,
)
from app.llm.prompts import (
    format_batch_disambiguation_prompt,
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


def _batch_lines() -> list[BatchLineInput]:
    return [
        BatchLineInput(
            line_no=1,
            raw_text="10 qop tsement",
            normalized_text="sement",
            candidates=[
                DisambiguationCandidateInput(canonical_id=10, name_uz="Sement M400"),
                DisambiguationCandidateInput(canonical_id=11, name_uz="Sement M500"),
            ],
        ),
        BatchLineInput(
            line_no=2,
            raw_text="500 dona kirpich",
            normalized_text="g'isht",
            candidates=[DisambiguationCandidateInput(canonical_id=20, name_uz="G'isht M100")],
        ),
    ]


def test_batch_prompt_carries_every_line_and_the_answer_language() -> None:
    payload = json.loads(format_batch_disambiguation_prompt(_batch_lines(), lang="ru"))

    assert payload["answer_language"] == "Russian"
    assert [line["line_no"] for line in payload["lines"]] == [1, 2]
    assert payload["lines"][0]["customer_text"] == "10 qop tsement"
    assert [c["id"] for c in payload["lines"][0]["candidates"]] == [10, 11]


def test_batch_prompt_defaults_to_uzbek_latin_for_an_unknown_language() -> None:
    payload = json.loads(format_batch_disambiguation_prompt(_batch_lines(), lang="de"))
    assert payload["answer_language"] == "Uzbek, Latin script"


def test_batch_response_keeps_the_question_and_drops_broken_rows() -> None:
    """A malformed row must vanish, not become a default.

    The caller keeps its deterministic decision for any line missing from the
    result, so dropping is safe -- inventing a canonical_id here would put a
    product the customer never named into their basket.
    """
    client = LLMClient()
    result = client._deserialize_batch(
        {
            "lines": [
                {
                    "line_no": 1,
                    "canonical_id": 10,
                    "confidence": 0.62,
                    "reason": "grade unclear",
                    "question": "M400 mi yoki M500?",
                },
                {"line_no": 2, "canonical_id": None, "confidence": 0.0, "question": ""},
                {"canonical_id": 30, "confidence": 0.9},
                {"line_no": 4, "canonical_id": "not-an-id", "confidence": 0.9},
                "nonsense",
            ]
        }
    )

    assert set(result.lines) == {1, 2}
    assert result.lines[1].question == "M400 mi yoki M500?"
    assert result.lines[1].canonical_id == 10
    # An empty question string is absence, not a question worth asking.
    assert result.lines[2].question is None


async def test_batch_mock_answers_every_line_without_a_session() -> None:
    client = LLMClient(mock_mode=True)
    result = await client.disambiguate_batch(_batch_lines())

    assert set(result.lines) == {1, 2}
    assert result.lines[1].canonical_id in (10, 11)
    assert result.lines[2].canonical_id == 20


async def test_batch_with_no_lines_makes_no_call() -> None:
    client = LLMClient(mock_mode=True)
    result = await client.disambiguate_batch([])
    assert result.lines == {}
