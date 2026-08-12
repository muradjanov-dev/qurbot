"""Cache key generation and lookup for LLM calls."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_llm_input_hash(
    purpose: str,
    prompt_version: str,
    payload: str | dict[str, Any],
) -> str:
    """Compute sha256 hash for LLM input to enable deterministic caching."""
    if isinstance(payload, dict):
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    else:
        payload_str = str(payload)

    raw_key = f"{purpose}:{prompt_version}:{payload_str}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
