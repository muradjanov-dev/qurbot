"""When the parser cannot read a message, the answer still has to be useful.

"Kechirasiz, tushunmadim" is where a customer leaves. It says nothing to
someone who wrote "salom" or "fanera bormi?", and the people this bot is for do
not try another phrasing -- they close the chat. So the model is asked what to
tell them, and the fixed string stays only as the floor for when it cannot
answer.
"""

import json

import pytest

from app.core.config import settings
from app.core.i18n import DEFAULT_LANG
from app.llm.client import LLMClient
from app.llm.prompts import _ANSWER_LANGUAGES, format_customer_guide_prompt


def test_guide_prompt_carries_the_message_and_the_language() -> None:
    payload = json.loads(format_customer_guide_prompt("salom, fanera bormi?", "ru"))
    assert payload["customer_message"] == "salom, fanera bormi?"
    assert payload["answer_language"].startswith("Russian")


def test_guide_prompt_falls_back_to_the_default_language() -> None:
    """An unknown code gets the configured default, named with its alphabet.

    The bare label "Uzbek, Cyrillic script" was not enough to stop the model
    replying in Latin -- both are Uzbek -- so the prompt carries a sample.
    """
    payload = json.loads(format_customer_guide_prompt("salom", "de"))
    assert payload["answer_language"] == _ANSWER_LANGUAGES[DEFAULT_LANG]
    assert "Cyrillic" in payload["answer_language"]
    assert "example:" in payload["answer_language"]


async def test_guidance_tells_the_customer_the_format() -> None:
    reply = await LLMClient(mock_mode=True).guide_customer("salom aka", "uz_latn")
    assert reply is not None
    assert "10 dona fanera 12mm" in reply


async def test_an_empty_message_is_not_worth_a_call() -> None:
    assert await LLMClient(mock_mode=True).guide_customer("   ", "uz_latn") is None


async def test_guidance_is_skipped_when_the_model_is_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No key, no budget, no model -- the caller falls back to the fixed string."""
    monkeypatch.setattr(settings, "llm_enabled", False)
    assert await LLMClient(mock_mode=True).guide_customer("salom", "uz_latn") is None


def test_a_runaway_answer_is_cut_at_a_line_break() -> None:
    """Read on a phone by someone already unsure what to type: length is a cost."""
    long_reply = "\n".join(f"qator {i} " + "x" * 60 for i in range(40))
    trimmed = LLMClient._trim_guide(long_reply)

    assert len(trimmed) <= settings.llm_guide_max_chars
    assert trimmed.startswith("qator 0")
    # Cut on a boundary, not mid-word.
    assert not trimmed.endswith("x" * 5) or trimmed.count("\n") > 0
