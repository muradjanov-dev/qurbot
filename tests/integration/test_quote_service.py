from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CanonicalProduct, District
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.domain.optimizer.models import BasketItemQuery, OptimizationStrategy
from app.services.quote_service import QuoteService
from scripts.seed import seed_database


@pytest.mark.asyncio
async def test_quote_service_optimization_against_seeded_db(test_session: AsyncSession) -> None:
    # 1. Seed database
    await seed_database(test_session)

    # 2. Setup repos & service
    shop_repo = ShopRepository(test_session)
    catalog_repo = CatalogRepository(test_session)
    quote_service = QuoteService(shop_repo, catalog_repo)

    # 3. Retrieve sample canonical products from catalog
    stmt = select(CanonicalProduct).limit(8)
    res = await test_session.execute(stmt)
    products = list(res.scalars().all())
    assert len(products) >= 5, "Database must have seeded canonical products"

    # 4. Construct multi-item basket
    basket_items = [
        BasketItemQuery(
            line_no=idx + 1,
            canonical_id=p.id,
            name_uz=p.name_uz,
            needed_qty=Decimal("10")
            if p.base_unit_code in ("kg", "litr", "metr")
            else Decimal("5"),
            unit_code=p.base_unit_code,
        )
        for idx, p in enumerate(products)
    ]

    # 5. Lookup Chilonzor district
    dist_stmt = select(District).where(District.name_uz == "Chilonzor")
    dist_res = await test_session.execute(dist_stmt)
    chilonzor = dist_res.scalars().first()
    district_id = chilonzor.id if chilonzor else 1

    # 6. Run quote optimization
    result = await quote_service.optimize_basket(
        basket_items=basket_items,
        district_id=district_id,
    )

    # 7. Assertions
    assert result.total_offers_evaluated > 0
    assert result.total_candidate_shops > 0
    assert len(result.variants) == 5
    assert len(result.deduplicated_variants) >= 1
    assert (
        result.solve_duration_ms < 1500.0
    ), f"Solve took {result.solve_duration_ms} ms (target < 1500 ms)"

    # Print ASCII summary of generated quotes
    sep = "=" * 90
    print(f"\n{sep}")
    print(
        f"OPTIMIZATION RESULT SUMMARY (Duration: {result.solve_duration_ms:.2f} ms | "
        f"Evaluated: {result.total_offers_evaluated} offers across "
        f"{result.total_candidate_shops} shops)"
    )
    print(sep)
    for idx, card in enumerate(result.deduplicated_variants, 1):
        strats = ", ".join(s.value for s in card.strategy_labels)
        print(f"Variant #{idx} [{strats}]:")
        print(
            f"  • Grand Total:    {card.grand_total_uzs:,} UZS "
            f"(Items: {card.items_total_uzs:,} + Delivery: {card.delivery_total_uzs:,})"
        )
        print(
            f"  • Coverage:       {card.covered_count}/{card.total_count} "
            f"({card.coverage_pct:.1f}%)"
        )
        print(f"  • Shops Used:     {len(card.shop_groups)} shops (Max ETA: {card.max_eta_hours}h)")
        print(f"  • Savings:        {card.savings_vs_worst_uzs:,} UZS ({card.savings_pct:.1f}%)")
        for g in card.shop_groups:
            print(
                f"     - Shop #{g.shop_id} ({g.shop_name}): {len(g.lines)} items, "
                f"Subtotal: {g.subtotal_uzs:,}, Delivery: {g.delivery_fee_uzs:,}"
            )
        print("-" * 90)

    # Check that cheapest total has lowest or equal grand total
    cheapest = next(
        v for v in result.variants if OptimizationStrategy.CHEAPEST_TOTAL in v.strategy_labels
    )
    for v in result.variants:
        if v.coverage_pct >= cheapest.coverage_pct:
            assert (
                cheapest.grand_total_uzs <= v.grand_total_uzs
                or cheapest.grand_total_uzs - v.grand_total_uzs < Decimal("5000")
            )
