"""Load test: 50 concurrent baskets end-to-end, p95 < 2s (SPEC §13).

Runs the full pipeline (parse -> match -> optimize) concurrently against a real
DB, each on its own session/connection, and reports p50/p95/p99 latency. Exits
non-zero if p95 exceeds the threshold, so it can gate CI.
"""

import asyncio
import logging
import time
from decimal import Decimal

from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import async_session_factory
from app.domain.optimizer.models import BasketItemQuery
from app.services.catalog_service import CatalogService
from app.services.quote_service import QuoteService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_test")

CONCURRENT_BASKETS = 50
P95_THRESHOLD_SECONDS = 2.0
SAMPLE_BASKET_TEXT = (
    "10 qop sement m400, 500 dona g'isht, 3 quti plitka 30x30, 2t qum, 15 qop rotband"
)


async def run_one_basket() -> float:
    start = time.monotonic()
    async with async_session_factory() as session:
        catalog_repo = CatalogRepository(session)
        ops_repo = OpsRepository(session)
        shop_repo = ShopRepository(session)
        catalog_service = CatalogService(catalog_repo, ops_repo)
        quote_service = QuoteService(shop_repo, catalog_repo)

        parsed_results = await catalog_service.parse_and_match_basket(SAMPLE_BASKET_TEXT)
        basket_items = [
            BasketItemQuery(
                line_no=line.line_no,
                canonical_id=decision.canonical_id,
                name_uz=line.parsed_name,
                needed_qty=line.qty,
                unit_code=line.unit_code or "dona",
            )
            for line, decision in parsed_results
            if decision.canonical_id is not None
        ]
        if basket_items:
            await quote_service.optimize_basket(basket_items)
        await session.commit()
    return time.monotonic() - start


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return sorted_values[index]


async def main() -> None:
    logger.info("Starting load test: %d concurrent baskets", CONCURRENT_BASKETS)
    durations = await asyncio.gather(*(run_one_basket() for _ in range(CONCURRENT_BASKETS)))
    sorted_durations = sorted(durations)

    p50 = _percentile(sorted_durations, 0.50)
    p95 = _percentile(sorted_durations, 0.95)
    p99 = _percentile(sorted_durations, 0.99)

    logger.info(
        "Results: p50=%.3fs p95=%.3fs p99=%.3fs max=%.3fs",
        p50,
        p95,
        p99,
        sorted_durations[-1],
    )

    if p95 > P95_THRESHOLD_SECONDS:
        raise SystemExit(
            f"FAILED: p95 {p95:.3f}s exceeds threshold {P95_THRESHOLD_SECONDS}s "
            f"({Decimal(str(p95)):.3f}s over {CONCURRENT_BASKETS} concurrent baskets)"
        )
    logger.info("PASSED: p95 %.3fs is within %.1fs threshold", p95, P95_THRESHOLD_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
