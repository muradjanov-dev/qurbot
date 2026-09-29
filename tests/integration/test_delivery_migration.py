"""Additive upgrade against a named disposable local PostgreSQL database."""

import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

URL = os.environ.get("DELIVERY_MIGRATION_TEST_DATABASE_URL")
TABLES = ("orders", "quotes", "order_shop_parts", "checkout_attempts")


async def _reset(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


async def _baseline(url: str) -> dict[str, list[dict[str, object]]]:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:

            async def insert(sql: str) -> int:
                return (await conn.execute(text(sql + " RETURNING id"))).scalar_one()

            user = await insert(
                "INSERT INTO users (full_name, lang, role, is_blocked) "
                "VALUES ('Legacy guest', 'uz_cyrl', 'customer', false)"
            )
            basket = await insert(
                f"INSERT INTO baskets (user_id, raw_text, status) "
                f"VALUES ({user}, 'Legacy order', 'ordered')"
            )
            quote = await insert(
                "INSERT INTO quotes (basket_id, strategy, items_total, delivery_total, "
                "grand_total, coverage_pct, shop_count, missing_line_ids, payload) "
                f"VALUES ({basket}, 'cheapest', 123456.78, 50000, 173456.78, 100, 1, "
                '\'[]\', \'{"fx_snapshot":{"version": 7,"rate":"11820.48"}}\')'
            )
            order = await insert(
                "INSERT INTO orders (quote_id, user_id, status, contact_phone, "
                "delivery_address, grand_total_quoted, grand_total_final) "
                f"VALUES ({quote}, {user}, 'fulfilled', '+998900000001', "
                "'Historical address', 173456.78, 173456.78)"
            )
            district = await insert(
                "INSERT INTO districts (name_uz, name_ru) VALUES ('Test', 'Test')"
            )
            shop = await insert(
                "INSERT INTO shops (name, phone, district_id, address) "
                f"VALUES ('Legacy house', '+998900000002', {district}, 'Test')"
            )
            await insert(
                "INSERT INTO order_shop_parts (order_id, shop_id, subtotal, delivery_fee, status) "
                f"VALUES ({order}, {shop}, 123456.78, 50000, 'accepted')"
            )
            await conn.execute(
                text(
                    "INSERT INTO checkout_attempts "
                    "(user_id, idempotency_key, fingerprint, order_id) "
                    f"VALUES ({user}, 'legacy-receipt', 'legacy-fingerprint', {order})"
                )
            )
            return {
                table: [
                    dict(row)
                    for row in (
                        await conn.execute(text(f"SELECT * FROM {table} ORDER BY 1"))
                    ).mappings()
                ]
                for table in TABLES
            }
    finally:
        await engine.dispose()


async def _verify(url: str, baseline: dict[str, list[dict[str, object]]]) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            for table, rows in baseline.items():
                current = (await conn.execute(text(f"SELECT * FROM {table} ORDER BY 1"))).mappings()
                assert [
                    {key: row[key] for key in old} for row, old in zip(current, rows, strict=True)
                ] == rows
            order = (await conn.execute(text("SELECT * FROM orders"))).mappings().one()
            assert order["workflow_revision"] == 0
            assert order["delivery_problem"] is False
            assert order["courier_cost_uzs"] is None
            for table in ("order_events", "order_notifications"):
                assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar() == 0
            assert (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar() == ("0027_order_delivery_workflow")
    finally:
        await engine.dispose()


@pytest.mark.skipif(not URL, reason="dedicated delivery migration DB not configured")
def test_additive_delivery_upgrade_preserves_legacy_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    assert URL is not None
    parsed = make_url(URL)
    assert (parsed.host, parsed.port, parsed.username, parsed.database) == (
        "127.0.0.1",
        5440,
        "qurbot_stage",
        "qurbot_delivery_migrations_test",
    ), "refuse migration reset outside the isolated database"
    monkeypatch.setattr(settings, "database_url", URL)
    config = Config("alembic.ini")
    asyncio.run(_reset(URL))
    command.upgrade(config, "0026_currency_sources")
    baseline = asyncio.run(_baseline(URL))
    command.upgrade(config, "head")
    asyncio.run(_verify(URL, baseline))
