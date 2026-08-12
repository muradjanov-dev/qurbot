"""Versioned prompt templates for LLM disambiguation and basket parsing."""

from __future__ import annotations

import json

from app.llm.models import DisambiguationCandidateInput

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
