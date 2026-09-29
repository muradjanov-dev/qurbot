"""Opt-in, end-to-end migration check on the dedicated disposable test database.

Run with TELEGRAM_CLEANUP_MIGRATION_TEST_DATABASE_URL set to the isolated
``qurbot_migrations_test`` database. The name/host/user guard below prevents
this migration-reset test from touching any other database.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.services.telegram_cleanup import register_transient_message

TEST_DATABASE_URL = os.environ.get("TELEGRAM_CLEANUP_MIGRATION_TEST_DATABASE_URL")


def _assert_isolated_database(database_url: str) -> None:
    parsed = make_url(database_url)
    if (
        parsed.database != "qurbot_migrations_test"
        or parsed.host != "127.0.0.1"
        or parsed.port != 5440
        or parsed.username != "qurbot_stage"
    ):
        raise AssertionError("Migration validation is restricted to the isolated local test DB")


async def _seed_finite_stock_offer(database_url: str) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    INSERT INTO districts (name_uz, name_ru)
                    SELECT 'Migration Test', 'Migration Test'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM districts WHERE name_uz = 'Migration Test'
                    )
                    RETURNING id
                    """
                )
            )
            district_id = result.scalar_one_or_none()
            if district_id is None:
                district_id = (
                    await connection.execute(
                        text("SELECT id FROM districts WHERE name_uz = 'Migration Test' LIMIT 1")
                    )
                ).scalar_one()

            await connection.execute(
                text(
                    """
                    INSERT INTO units (code, name_uz, name_ru, dimension)
                    VALUES ('mt_unit', 'test unit', 'test unit', 'count')
                    ON CONFLICT (code) DO NOTHING
                    """
                )
            )
            category_result = await connection.execute(
                text(
                    """
                    INSERT INTO categories (slug, name_uz, name_ru)
                    VALUES ('migration-test-category', 'Test', 'Test')
                    ON CONFLICT (slug) DO NOTHING
                    RETURNING id
                    """
                )
            )
            category_id = category_result.scalar_one_or_none()
            if category_id is None:
                category_id = (
                    await connection.execute(
                        text("SELECT id FROM categories " "WHERE slug = 'migration-test-category'")
                    )
                ).scalar_one()

            shop_result = await connection.execute(
                text(
                    """
                    INSERT INTO shops (name, phone, district_id, address)
                    SELECT 'Migration Test Shop', '+998000000001', :district_id,
                           'Isolated migration test'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM shops
                        WHERE name = 'Migration Test Shop' AND phone = '+998000000001'
                    )
                    RETURNING id
                    """
                ),
                {"district_id": district_id},
            )
            shop_id = shop_result.scalar_one_or_none()
            if shop_id is None:
                shop_id = (
                    await connection.execute(
                        text(
                            "SELECT id FROM shops WHERE name = 'Migration Test Shop' "
                            "AND phone = '+998000000001' LIMIT 1"
                        )
                    )
                ).scalar_one()

            product_result = await connection.execute(
                text(
                    """
                    INSERT INTO canonical_products (
                        slug, name_uz, name_uz_cyrl, name_ru, category_id,
                        base_unit_code, search_doc
                    )
                    VALUES (
                        'migration-test-finite-stock', 'Test product', 'Test product',
                        'Test product', :category_id, 'mt_unit',
                        'finite stock migration validation'
                    )
                    ON CONFLICT (slug) DO NOTHING
                    RETURNING id
                    """
                ),
                {"category_id": category_id},
            )
            product_id = product_result.scalar_one_or_none()
            if product_id is None:
                product_id = (
                    await connection.execute(
                        text(
                            "SELECT id FROM canonical_products "
                            "WHERE slug = 'migration-test-finite-stock'"
                        )
                    )
                ).scalar_one()

            offer_result = await connection.execute(
                text(
                    """
                    INSERT INTO shop_products (
                        shop_id, canonical_id, raw_name, raw_unit, pack_size,
                        pack_unit_code, price_per_pack, price_per_base_unit,
                        stock_status, stock_qty
                    )
                    VALUES (
                        :shop_id, :product_id, 'Test product', 'mt_unit', 1,
                        'mt_unit', 12345, 12345, 'in_stock', 17
                    )
                    ON CONFLICT ON CONSTRAINT uq_shop_products_offer DO UPDATE SET
                        price_per_pack = EXCLUDED.price_per_pack,
                        price_per_base_unit = EXCLUDED.price_per_base_unit,
                        stock_status = EXCLUDED.stock_status,
                        stock_qty = EXCLUDED.stock_qty
                    RETURNING id
                    """
                ),
                {"shop_id": shop_id, "product_id": product_id},
            )
            offer_id = offer_result.scalar_one()
            history_exists = (
                await connection.execute(
                    text(
                        "SELECT 1 FROM price_history WHERE shop_product_id = :offer_id "
                        "AND price_per_pack = 12345 LIMIT 1"
                    ),
                    {"offer_id": offer_id},
                )
            ).scalar_one_or_none()
            if history_exists is None:
                await connection.execute(
                    text(
                        "INSERT INTO price_history "
                        "(shop_product_id, price_per_pack, price_per_base_unit) "
                        "VALUES (:offer_id, 12345, 12345)"
                    ),
                    {"offer_id": offer_id},
                )
            finite_stock = (
                await connection.execute(
                    text("SELECT stock_qty FROM shop_products WHERE id = :offer_id"),
                    {"offer_id": offer_id},
                )
            ).scalar_one()
            assert finite_stock == 17
            return offer_id
    finally:
        await engine.dispose()


async def _verify_offer_and_registry(database_url: str, offer_id: int) -> None:
    engine = create_async_engine(database_url)
    now = datetime.now(UTC)
    chat_id = 1_900_000_101
    try:
        async with engine.begin() as connection:
            offer = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT sp.stock_qty, sp.price_per_pack, sp.price_per_base_unit,
                               sp.stock_status, count(ph.id) AS history_count,
                               min(ph.price_per_pack) AS history_price
                        FROM shop_products sp
                        LEFT JOIN price_history ph ON ph.shop_product_id = sp.id
                        WHERE sp.id = :offer_id
                        GROUP BY sp.id
                        """
                        ),
                        {"offer_id": offer_id},
                    )
                )
                .mappings()
                .one()
            )
            assert offer["stock_qty"] is None
            assert offer["price_per_pack"] == 12345
            assert offer["price_per_base_unit"] == 12345
            assert offer["stock_status"] == "in_stock"
            assert offer["history_count"] >= 1
            assert offer["history_price"] == 12345
            version = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            assert version == "0025_telegram_cleanup"
            table_exists = (
                await connection.execute(
                    text("SELECT to_regclass('public.telegram_messages') " "IS NOT NULL AS exists")
                )
            ).scalar_one()
            assert table_exists

        # Use the real service so its PostgreSQL ON CONFLICT and generated PK
        # sequence are tested alongside the migration-created schema.
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.db.models.telegram_message import TelegramMessage

        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            for message_id in (1, 1, 2):
                await register_transient_message(
                    session,
                    chat_id=chat_id,
                    message_id=message_id,
                    message_type="ai_customer_inbound",
                    sent_at=now,
                )
            await session.commit()
            rows = list(
                (
                    await session.scalars(
                        select(TelegramMessage)
                        .where(TelegramMessage.chat_id == chat_id)
                        .order_by(TelegramMessage.message_id)
                    )
                ).all()
            )
            assert len(rows) == 2
            assert rows[0].id > 0 and rows[1].id > rows[0].id
            assert rows[0].due_at == now + timedelta(hours=24)
            await session.execute(
                text("DELETE FROM telegram_messages WHERE chat_id = :chat_id"),
                {"chat_id": chat_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


def test_telegram_cleanup_migrations_preserve_finite_stock_history(monkeypatch):
    if not TEST_DATABASE_URL:
        pytest.skip("set TELEGRAM_CLEANUP_MIGRATION_TEST_DATABASE_URL for isolated PostgreSQL test")
    _assert_isolated_database(TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))

    command.downgrade(config, "0023_default_lang_cyrillic")
    offer_id = asyncio.run(_seed_finite_stock_offer(TEST_DATABASE_URL))
    command.upgrade(config, "0025_telegram_cleanup")
    asyncio.run(_verify_offer_and_registry(TEST_DATABASE_URL, offer_id))


async def _currency_migration_fixture(database_url: str, offer_id: int) -> dict:
    """Use pre-migration SQL, so current ORM defaults cannot hide backfill errors."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE shop_products SET price_per_pack=12345.67, "
                    "price_per_base_unit=12345.6700, stock_qty=NULL WHERE id=:id"
                ),
                {"id": offer_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO shop_product_price_tiers (shop_product_id,min_qty,price_per_pack) "
                    "VALUES (:id,200,12000.25) ON CONFLICT (shop_product_id,min_qty) "
                    "DO UPDATE SET price_per_pack=EXCLUDED.price_per_pack"
                ),
                {"id": offer_id},
            )
            user_id = (
                await connection.execute(
                    text(
                        "INSERT INTO users (tg_id,full_name) VALUES (1900000102,'FX "
                        "migration test') "
                        "ON CONFLICT (tg_id) DO UPDATE SET full_name=EXCLUDED.full_name "
                        "RETURNING id"
                    )
                )
            ).scalar_one()
            basket_id = (
                await connection.execute(
                    text(
                        "INSERT INTO baskets (user_id,raw_text,status) VALUES "
                        "(:uid,'migration','ordered') "
                        "RETURNING id"
                    ),
                    {"uid": user_id},
                )
            ).scalar_one()
            quote_id = (
                await connection.execute(
                    text(
                        "INSERT INTO quotes "
                        "(basket_id,strategy,items_total,delivery_total,grand_total,"
                        "coverage_pct,shop_count,payload) VALUES "
                        "(:bid,'cheapest',12345.67,50000,62345.67,"
                        '100,1,\'{"historical_price":"12345.67"}\') RETURNING id'
                    ),
                    {"bid": basket_id},
                )
            ).scalar_one()
            await connection.execute(
                text(
                    "INSERT INTO orders (quote_id,user_id,status,contact_phone,delivery_address,"
                    "grand_total_quoted,grand_total_final) VALUES (:qid,:uid,'confirmed',"
                    "'+998000000002','Isolated test',62345.67,62345.67)"
                ),
                {"qid": quote_id, "uid": user_id},
            )
            return await _currency_snapshot(connection)
    finally:
        await engine.dispose()


async def _currency_snapshot(connection) -> dict:
    # Exact snapshots of old columns include timestamps and historical records.
    result = {}
    for table in ("shop_products", "shop_product_price_tiers", "quotes", "orders", "price_history"):
        result[table] = (
            await connection.execute(
                text(
                    f"SELECT coalesce(jsonb_agg(to_jsonb(t) - ARRAY['source_currency',"
                    f"'source_price_per_pack','fx_rate_used','fx_rate_revision'] ORDER "
                    f"BY id), '[]'::jsonb) "
                    f"FROM {table} t"
                )
            )
        ).scalar_one()
    return result


async def _verify_currency_migration(database_url: str, before: dict) -> None:
    from decimal import Decimal

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await _currency_snapshot(connection) == before
            from sqlalchemy import CheckConstraint

            from app.db.base import Base

            for table_name in (
                "fx_rate_settings",
                "shop_products",
                "shop_product_price_tiers",
                "import_batches",
            ):
                expected = {
                    constraint.name
                    for constraint in Base.metadata.tables[table_name].constraints
                    if isinstance(constraint, CheckConstraint)
                }
                actual = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT conname FROM pg_constraint "
                                "WHERE contype='c' AND conrelid=to_regclass(:table)"
                            ),
                            {"table": table_name},
                        )
                    ).scalars()
                )
                assert actual == expected, (table_name, actual, expected)
            rate = (
                await connection.execute(
                    text(
                        "SELECT usd_to_uzs_rate,revision,updated_by FROM fx_rate_settings "
                        "WHERE id=1"
                    )
                )
            ).one()
            assert rate == (Decimal("11820.48"), 1, None)
            for table in ("shop_products", "shop_product_price_tiers"):
                mismatch = (
                    await connection.execute(
                        text(
                            f"SELECT count(*) FROM {table} WHERE source_currency <> 'UZS' "
                            "OR source_price_per_pack IS DISTINCT FROM price_per_pack "
                            "OR fx_rate_used IS DISTINCT FROM 1 OR fx_rate_revision <> 0"
                        )
                    )
                ).scalar_one()
                assert mismatch == 0
            assert (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one() == "0026_currency_sources"
    finally:
        await engine.dispose()


def test_currency_migration_preserves_prices_tiers_and_confirmed_orders(monkeypatch):
    if not TEST_DATABASE_URL:
        pytest.skip("set TELEGRAM_CLEANUP_MIGRATION_TEST_DATABASE_URL for isolated PostgreSQL test")
    _assert_isolated_database(TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "database_url", TEST_DATABASE_URL)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "0025_telegram_cleanup")
    offer_id = asyncio.run(_seed_finite_stock_offer(TEST_DATABASE_URL))
    before = asyncio.run(_currency_migration_fixture(TEST_DATABASE_URL, offer_id))
    command.upgrade(config, "0026_currency_sources")
    asyncio.run(_verify_currency_migration(TEST_DATABASE_URL, before))
