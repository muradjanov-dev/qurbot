"""Isolated PostgreSQL matching evaluation; never accepts the production DB.

Set EVAL_DATABASE_URL to a dedicated database named qurbot_matching_eval.
The fixed corpus predates tuning; --split holdout is for final evaluation only.
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

from sqlalchemy import insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.repositories.catalog_repo import CatalogRepository
from app.domain.matching.safety import attributes_verified
from app.domain.normalize.text import normalize_query
from app.domain.parsing.parser import parse_basket_lines
from app.llm.client import LLMClient, close_http_client, start_http_client
from app.llm.pricing import EvaluationBudget
from app.services.catalog_service import CatalogService

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


class EvaluationClient(LLMClient):
    """Local per-model cache/accounting; no production alerts or writes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache = {}
        self.calls = []
        self.cache_hits = 0

    async def _get_cached_call(self, input_hash):
        value = self.cache.get(input_hash)
        if value is not None:
            self.cache_hits += 1
        return value

    async def _record_call(self, **kwargs):
        self.calls.append(
            {
                "input_tokens": kwargs["input_tokens"],
                "output_tokens": kwargs["output_tokens"],
                "estimated_cost": str(kwargs["cost_usd"]),
                "outcome": self.last_outcome,
                "attempts": self.last_attempt_count,
            }
        )
        if self.last_outcome == "success":
            self.cache[kwargs["input_hash"]] = kwargs["raw_response"]


async def run(split: str, models: list[str]) -> dict:
    url = make_url(os.environ["EVAL_DATABASE_URL"])
    if url.database != "qurbot_matching_eval" or not url.drivername.startswith("postgresql"):
        raise ValueError("Only isolated PostgreSQL qurbot_matching_eval is allowed")
    engine = create_async_engine(url)
    snapshot = json.loads((FIXTURES / "catalog_snapshot.json").read_text())
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
        existing = await conn.scalar(select(CanonicalProduct.id).limit(1))
        if existing is None:
            for model in (Unit, Category, CanonicalProduct):
                rows = snapshot[model.__tablename__]
                for row in rows:
                    for key in ("reference_price", "factor_to_base"):
                        if row.get(key) is not None:
                            row[key] = Decimal(row[key])
                await conn.execute(insert(model.__table__), rows)
        await conn.execute(text("ANALYZE canonical_products"))
    cases = json.loads((FIXTURES / "matching_eval.json").read_text())
    cases = [case for case in cases if split == "all" or case["split"] == split]
    budget = EvaluationBudget(
        reserved=Decimal(os.environ.get("EVAL_PRIOR_RESERVED_USD", "0")),
        ledger_path=FIXTURES.parents[1] / ".pytest_cache" / "llm-eval-budget.json",
    )
    if not 0 <= budget.reserved <= budget.limit:
        raise ValueError("Invalid previous experiment reservation")
    report = {"split": split, "catalog_rows": len(snapshot["canonical_products"]), "models": {}}
    await start_http_client()
    try:
        for model in models:
            settings.llm_enabled = model != "deterministic"
            records = []
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                repo = CatalogRepository(session)
                repo.record_alias_hit = AsyncMock()
                repo.create_unapproved_alias = AsyncMock()
                llm = EvaluationClient(model=model, evaluation_budget=budget)
                service = CatalogService(repo, AsyncMock(), llm)
                for case in cases:
                    started = time.perf_counter()
                    parsed = parse_basket_lines(case["query"])
                    matches = [
                        await service._match_deterministic(line, require_offers=True)
                        for line in parsed
                    ]
                    top_ids = [c.canonical_id for m in matches for c in m.candidates[:8]]
                    results = await service.parse_and_match_basket(
                        case["query"], require_offers=True
                    )
                    decisions = [d for _, d in results]
                    expected = case["expected"]
                    if expected == "match":
                        correct = bool(decisions) and all(
                            d.status == "auto_accept" and d.canonical_id in case["ids"]
                            for d in decisions
                        )
                    elif expected == "clarify":
                        correct = bool(decisions) and all(
                            d.status != "auto_accept" and d.clarify_question for d in decisions
                        )
                    elif expected == "invalid":
                        correct = bool(decisions) and all(
                            d.method == "invalid_qty" for d in decisions
                        )
                    else:
                        correct = bool(decisions) and all(
                            d.status == "unresolved" and d.canonical_id is None for d in decisions
                        )
                    unsafe = any(
                        d.status == "auto_accept"
                        and any(
                            not attributes_verified(normalize_query(p.raw_text), c.attributes)
                            for c in d.candidates
                            if c.canonical_id == d.canonical_id
                        )
                        for p, d in results
                    )
                    records.append(
                        {
                            "id": case["id"],
                            "correct": bool(correct),
                            "unsafe": unsafe,
                            "top8": bool(set(top_ids) & set(case["ids"])) if case["ids"] else None,
                            "ms": round((time.perf_counter() - started) * 1000, 2),
                            "status": [d.status for d in decisions],
                            "outcome": llm.last_outcome,
                        }
                    )
                    if llm.last_outcome == "budget_exhausted":
                        break
                    warm_started = time.perf_counter()
                    await service.parse_and_match_basket(case["query"], require_offers=True)
                    records[-1]["warm_ms"] = round((time.perf_counter() - warm_started) * 1000, 2)
                await session.rollback()
            timings = sorted(r["ms"] for r in records)
            top8 = [r["top8"] for r in records if r["top8"] is not None]
            report["models"][model] = {
                "count": len(records),
                "accuracy": sum(r["correct"] for r in records) / len(records),
                "unsafe_auto": sum(r["unsafe"] for r in records),
                "top8_recall": sum(top8) / len(top8) if top8 else None,
                "p50_ms": timings[math.ceil(len(timings) * 0.5) - 1],
                "p95_ms": timings[math.ceil(len(timings) * 0.95) - 1],
                "records": records,
                "llm_calls": llm.calls,
                "cache_hits": llm.cache_hits,
            }
    finally:
        await close_http_client()
        await engine.dispose()
    report["reserved_cost_upper_bound_usd"] = str(budget.reserved)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["development", "holdout", "all"], default="development")
    parser.add_argument("--models", nargs="+", default=["deterministic"])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--key-stdin", action="store_true", help="Read API key without exposing argv/env"
    )
    args = parser.parse_args()
    if args.key_stdin:
        settings.openai_api_key = sys.stdin.read().strip()
        if not settings.openai_api_key:
            raise SystemExit("Missing evaluation API key")
    report = json.dumps(asyncio.run(run(args.split, args.models)), indent=2)
    if args.output:
        args.output.write_text(report + "\n")
    else:
        print(report)
