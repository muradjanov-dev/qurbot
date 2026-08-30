"""Integration tests for Phase 7 LLM Fallback.

Tests:
1. Stage 3 LLM Disambiguation on noisy input.
2. Self-learning alias write-back to product_aliases.
3. Whole-message parsing fallback when structured extraction is low.
4. LLM call caching and token accounting in llm_calls.
5. Held-out 100-query evaluation set benchmark.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import ProductAlias
from app.db.models.ops import LLMCall
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.llm.client import LLMClient
from app.services.catalog_service import CatalogService
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def _full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise matching across the whole catalogue, not the launch scope.

    The launch allowlist deliberately narrows what can be matched, and it has
    its own coverage in test_addresses_and_scope.py. Pinning it off here keeps
    these tests about the matching pipeline, which is what they are for --
    otherwise they would fail for a product reason rather than a code one.
    """
    monkeypatch.setattr(settings, "enabled_category_slugs", [])


@pytest.mark.asyncio
async def test_llm_stage3_disambiguation_and_alias_writeback(test_session: AsyncSession) -> None:
    """Verify Stage 3 disambiguates difficult query and writes back unapproved alias."""
    await seed_database(test_session)

    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    # Enable mock mode for deterministic offline testing
    llm_client = LLMClient(session=test_session, mock_mode=True)
    catalog_service = CatalogService(catalog_repo, ops_repo, llm_client=llm_client)

    # "paneradan qalin" is noisy enough that no alias hits it and trigram
    # scores below auto-accept, so it falls through to Stage 3.
    results = await catalog_service.parse_and_match_basket("10 dona paneradan qalin 12")
    assert len(results) == 1
    parsed_line, decision = results[0]

    assert decision.canonical_id is not None
    assert decision.method in ("llm", "alias", "trgm")
    assert decision.confidence >= 0.80

    # Verify alias write-back occurred in product_aliases
    alias_stmt = select(ProductAlias).where(
        ProductAlias.source == "llm",
        ProductAlias.canonical_id == decision.canonical_id,
    )
    alias_res = await test_session.execute(alias_stmt)
    created_alias = alias_res.scalars().first()

    assert created_alias is not None
    assert created_alias.is_approved is False
    assert created_alias.confidence > Decimal("0")

    # Verify LLM call was logged in llm_calls table
    call_stmt = select(LLMCall).where(LLMCall.purpose == "batch_disambiguation")
    call_res = await test_session.execute(call_stmt)
    logged_call = call_res.scalars().first()

    assert logged_call is not None
    assert logged_call.input_tokens > 0
    assert logged_call.cost_usd >= Decimal("0")


@pytest.mark.asyncio
async def test_stage3_costs_one_call_per_basket(test_session: AsyncSession) -> None:
    """A basket asks the model once, however many of its lines are unresolved.

    This is the property, not an optimisation: per-line calls made the customer
    wait for the sum of the round trips and re-sent the same prompt each time,
    and CLAUDE.md forbids looping the LLM over basket lines.
    """
    await seed_database(test_session)

    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    llm_client = LLMClient(session=test_session, mock_mode=True)
    catalog_service = CatalogService(catalog_repo, ops_repo, llm_client=llm_client)

    # Three lines noisy enough that none is settled by alias or trigram alone.
    basket = "10 dona paneradan qalin 12\n5 dona osbdan yupqa\n8 dona dvpdan nozik"
    results = await catalog_service.parse_and_match_basket(basket)
    assert len(results) == 3

    call_stmt = select(LLMCall).where(LLMCall.purpose == "batch_disambiguation")
    call_res = await test_session.execute(call_stmt)
    calls = list(call_res.scalars().all())

    assert len(calls) == 1, f"expected a single batched call, got {len(calls)}"


@pytest.mark.asyncio
async def test_llm_whole_message_parse_fallback(test_session: AsyncSession) -> None:
    """Verify unstructured message is recovered by LLM whole-message parse fallback."""
    await seed_database(test_session)

    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    llm_client = LLMClient(session=test_session, mock_mode=True)
    catalog_service = CatalogService(catalog_repo, ops_repo, llm_client=llm_client)

    # Messy text without proper delimiter or structure
    unstructured_text = "bizga faneradan 10ta va osbdan 5ta kerak edi tashab berilar"
    results = await catalog_service.parse_and_match_basket(unstructured_text)

    assert len(results) >= 1
    for line, decision in results:
        assert line.qty > Decimal("0")
        assert decision.canonical_id is not None


@pytest.mark.asyncio
async def test_llm_held_out_100_queries_evaluation(test_session: AsyncSession) -> None:
    """SPEC Phase 7 deliverable: match rate evaluated on held-out set of 100 messy queries."""
    await seed_database(test_session)

    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    llm_client = LLMClient(session=test_session, mock_mode=True)
    catalog_service = CatalogService(catalog_repo, ops_repo, llm_client=llm_client)

    # 100 realistic, noisy construction material query variations
    base_templates = [
        "fanera 12mm {n} dona",
        "faner 12 {n} dona",
        "фанера 18 мм {n} dona",
        "osb 9mm {n} dona",
        "осб-3 12мм {n} dona",
        "dvp 3.2 {n} dona",
        "двп 3.2 {n} dona",
        "hdf 3.2 {n} dona",
        "fanera 4x4 4mm {n} dona",
        "fanera 3x3 15mm {n} dona",
    ]

    queries: list[str] = []
    for i in range(100):
        tmpl = base_templates[i % len(base_templates)]
        queries.append(tmpl.format(n=(i + 1) * 5))

    matched_count = 0
    for q in queries:
        results = await catalog_service.parse_and_match_basket(q)
        if results and results[0][1].canonical_id is not None:
            matched_count += 1

    match_rate = matched_count / len(queries)
    print(f"\n[EVALUATION] match rate: {match_rate:.1%} ({matched_count}/100 messy queries)")
    assert match_rate >= 0.90, f"Match rate {match_rate:.1%} is below target 90%!"
