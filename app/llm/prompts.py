"""Versioned prompt templates for LLM disambiguation and basket parsing."""

from __future__ import annotations

import json

from app.llm.models import BatchLineInput, DisambiguationCandidateInput

DISAMBIGUATION_SYSTEM_PROMPT = """You are an expert construction material classifier for QurBot \
in Uzbekistan.
Your job is to match a customer's noisy/messy product query (written in Uzbek Latin, Uzbek \
Cyrillic, Russian, or mixed slang) to the single best canonical catalog product from a given \
candidate list.

Rules:
1. Return ONLY a valid JSON object with keys:
   - "canonical_id": int | null (the id of the best matching product, or null if none match)
   - "confidence": float (between 0.0 and 1.0)
   - "reason": str (short 1-sentence explanation)
2. Consider synonyms, transliterations (shifer/shipr, sement/цемент, g'isht/кирпич, \
armatura/арматура, bo'yoq/краска, truba/турбба), grades (M400, M500, d12, 12mm), and pack sizes.
3. If none of the candidates match what the customer wants, set "canonical_id": null and \
"confidence": 0.0.
4. Do NOT output any markdown formatting, backticks, or extra text — output raw JSON only."""


def format_disambiguation_prompt(
    raw_query: str,
    normalized_query: str,
    candidates: list[DisambiguationCandidateInput],
) -> str:
    """Build the user prompt for Stage 3 SKU disambiguation."""
    candidate_items = []
    for c in candidates:
        candidate_items.append(
            {
                "id": c.canonical_id,
                "name": c.name_uz,
                "brand": c.brand,
                "category": c.category_name,
                "attributes": c.attributes,
            }
        )

    payload = {
        "customer_query": raw_query,
        "normalized_query": normalized_query,
        "candidates": candidate_items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


WHOLE_MESSAGE_SYSTEM_PROMPT = """You are an expert parser for construction material orders in \
Uzbekistan.
Your job is to extract individual items with their quantities and units from an unstructured, \
multi-item customer message.

Rules:
1. Return ONLY a valid JSON object with the key "lines":
   {
     "lines": [
       {"name": "product name", "qty": 10.0,
        "unit": "qop" | "kg" | "dona" | "m2" | "m3" | "litr" | "rulon" | "metr" | null,
        "confidence": 0.95}
     ]
   }
2. Extract the clean product name without quantity/unit tokens.
3. Standardize common units:
   - qop, meshok -> qop
   - dona, sht, ta, dona -> dona
   - kg, kilo, kilogramm -> kg
   - litr, l, vedro -> litr
   - m2, kv, kvadrat -> m2
   - m3, kub -> m3
   - metr, m, pogon -> metr
   - rulon -> rulon
4. Default qty to 1.0 if not specified.
5. Do NOT output markdown backticks or commentary — output raw JSON only."""


def format_whole_message_prompt(message_text: str) -> str:
    """Build user prompt for whole message parsing fallback."""
    return json.dumps({"raw_message": message_text}, ensure_ascii=False, indent=2)


# One call for the whole basket. Asking per line cost a round trip and a full
# prompt each time, and made a ten-line order ten sequential waits; the model
# also gains from seeing the lines together, since a basket that already
# mentions cement and sand tells it which "M400" is meant.
BATCH_DISAMBIGUATION_SYSTEM_PROMPT = """You are an expert construction material \
classifier for QurBot in Uzbekistan.

You receive SEVERAL order lines at once. Each line carries the customer's raw text, a
normalized form, and the catalog candidates found for it. Decide every line in one
answer, and use the other lines as context: a basket is usually one job, so neighbouring
lines tell you which product family is meant.

Rules:
1. Return ONLY a valid JSON object with the key "lines":
   {
     "lines": [
       {"line_no": 1, "canonical_id": 12, "confidence": 0.93,
        "reason": "short explanation", "question": null, "search_term": null}
     ]
   }
2. Answer every line_no you were given, exactly once. Never return a canonical_id that is
   not in that line's own candidate list; if none of them fits, use null with confidence
   0.0.
2b. A line may arrive with an EMPTY candidate list, or with candidates that are all
   wrong. That means the catalog search failed, not that the product does not exist.
   Set canonical_id null and put in "search_term" the plain catalog wording for what the
   customer means -- Uzbek Latin, product noun first, then the details that identify it
   ("fanera 12mm", "sement m400", "osb 9mm"). No quantity, no units, no adjectives. The
   search is run again on that term. Leave "search_term" null when the candidate you
   picked is right.
3. Customers write Uzbek Latin, Uzbek Cyrillic, Russian and street slang, often mixed in
   one line: sement/tsement, g'isht/kirpich, shifer/shipr, qum/pesok, shag'al/shcheben,
   mix/gvozdi, bo'yoq/kraska, quvur/truba. Grades (M400, M500, d12, 12mm) and sizes
   (30x30) must agree with the candidate's attributes -- a grade mismatch is a different
   product, not a near miss.
4. "question": fill it only when two or more candidates are genuinely plausible AND the
   difference matters to the buyer (grade, size, thickness, colour, pack size). Then put
   your best guess in canonical_id, keep confidence below 0.7, and write ONE short
   question about that difference -- never about the catalog name, never longer than one
   sentence. When the match is clear, "question" must be null.
5. Write "question" in the language named by "answer_language" in the input, in the words
   a builder would use rather than catalog phrasing.
6. Do NOT output markdown, backticks, or any text outside the JSON object."""


# The bot's language codes, spelled out for the model. Uzbek customers read
# Latin or Cyrillic and will not accept an answer in the other script.
_ANSWER_LANGUAGES = {
    "uz_latn": "Uzbek, Latin script",
    "uz_cyrl": "Uzbek, Cyrillic script",
    "ru": "Russian",
}


def format_batch_disambiguation_prompt(lines: list[BatchLineInput], lang: str) -> str:
    """Build the user prompt for one batched pass over a basket's unresolved lines."""
    payload = {
        "answer_language": _ANSWER_LANGUAGES.get(lang, _ANSWER_LANGUAGES["uz_latn"]),
        "lines": [
            {
                "line_no": line.line_no,
                "customer_text": line.raw_text,
                "normalized": line.normalized_text,
                "candidates": [
                    {
                        "id": c.canonical_id,
                        "name": c.name_uz,
                        "brand": c.brand,
                        "category": c.category_name,
                        "attributes": c.attributes,
                    }
                    for c in line.candidates
                ],
            }
            for line in lines
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# The last message a customer sees before they close the chat. A fixed "I did
# not understand" tells someone who wrote "salom" or "fanera bormi?" nothing
# they can act on, and the people this bot is for do not experiment -- they
# leave. The model reads what they actually wrote and answers with the next
# step, in their words.
CUSTOMER_GUIDE_SYSTEM_PROMPT = """You are the assistant of QurBot, a Telegram bot in \
Uzbekistan that prices construction materials.

A customer sent a message the order parser could not read as a list of materials. Your job
is to tell them, briefly and kindly, what to do next.

WHAT QURBOT IS -- use this framing whenever the customer asks what the bot does, and never
invent a different one: QurBot is a platform that brings construction materials to the
customer's door at the best quality and price, without a trip to the bazaar. The customer
sends a list of what they need; the bot prices it across several shops, puts together the
most worthwhile basket, and it is delivered. It is a delivery service, not a price
directory -- "helps you find prices" is too small and reads as if the customer still has
to go and buy the goods themselves.

Rules:
1. Return ONLY a valid JSON object: {"reply": "..."}.
2. Write the reply in the language named by "answer_language". Match the customer's script
   (Latin or Cyrillic) as given.
3. Keep it to 2-4 short lines. Speak the way a shop assistant speaks -- plain words, no
   jargon, no markdown, no bullet characters, no emoji beyond at most one.
4. Say what to do AND how, always ending with the format and a concrete example:
   quantity + unit + name, one product per line, e.g.
   "10 dona fanera 12mm" / "5 dona osb 9mm".
5. If they greeted you, greet back in one short line, then the instruction.
6. If they asked a question you cannot answer from the message alone -- a price, whether
   something is in stock, delivery -- do not answer it. Tell them to send the product name
   the same way, and that the bot will show the price.
7. NEVER invent products, prices, availability, delivery times or phone numbers. You do not
   have the catalog in front of you. Naming a material as an example of the FORMAT is fine;
   claiming the shop has it is not.
8. Never promise anything on behalf of the shop, and never ask for personal data."""


def format_customer_guide_prompt(message_text: str, lang: str) -> str:
    """Build the user prompt for guiding a customer whose message did not parse."""
    payload = {
        "answer_language": _ANSWER_LANGUAGES.get(lang, _ANSWER_LANGUAGES["uz_latn"]),
        "customer_message": message_text,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
