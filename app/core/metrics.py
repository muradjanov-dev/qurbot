"""Prometheus metric objects (SPEC §12). Instrumented at their call sites in
quote_service, catalog_service, and llm/client; scraped via /metrics."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

quote_latency_seconds = Histogram(
    "qurbot_quote_latency_seconds",
    "Basket quote generation latency",
    buckets=(0.01, 0.05, 0.1, 0.3, 1.0, 2.0, 5.0),
)

match_method_total = Counter(
    "qurbot_match_method_total",
    "Count of basket lines matched by method",
    ["method"],
)

llm_cost_usd_total = Counter(
    "qurbot_llm_cost_usd_total",
    "Cumulative LLM spend in USD",
)

stale_price_offers = Gauge(
    "qurbot_stale_price_offers",
    "Active offers currently marked stale",
)

db_pool_size = Gauge(
    "qurbot_db_pool_size",
    "Configured DB connection pool size",
)

db_pool_checked_out = Gauge(
    "qurbot_db_pool_checked_out",
    "DB connections currently checked out of the pool",
)
