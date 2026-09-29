from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fx import FxRateSetting
from app.db.models.shop import PriceHistory, ShopProduct, ShopProductPriceTier
from app.services.fx_pricing import FxPricingError, FxPricingService


@pytest.mark.asyncio
async def test_uzs_offer_write_keeps_canonical_amount_and_records_uzs_source(
    test_session: AsyncSession,
) -> None:
    offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Boards",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("1"),
        price_per_base_unit=Decimal("1"),
    )
    test_session.add(offer)

    canonical = await FxPricingService(test_session).set_offer_price(
        offer,
        amount=Decimal("1250.50"),
        currency="UZS",
        base_unit_code="dona",
        updated_by="admin",
    )

    assert canonical == Decimal("1250.50")
    assert offer.currency == "UZS"
    assert offer.source_currency == "UZS"
    assert offer.source_price_per_pack == Decimal("1250.5000")
    assert offer.fx_rate_used == Decimal("1.000000")
    assert offer.fx_rate_revision == 0
    history = await test_session.scalar(
        select(PriceHistory).where(PriceHistory.shop_product_id == offer.id)
    )
    assert history is not None
    assert history.price_per_pack == Decimal("1250.50")


@pytest.mark.asyncio
async def test_usd_offer_write_requires_a_configured_rate_without_persisting_placeholder(
    test_session: AsyncSession,
) -> None:
    offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Boards",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("1"),
        price_per_base_unit=Decimal("1"),
    )

    with pytest.raises(FxPricingError, match="rate_required"):
        await FxPricingService(test_session).set_offer_price(
            offer,
            amount=Decimal("4.80"),
            currency="USD",
            base_unit_code="dona",
        )

    assert await test_session.scalar(select(func.count(ShopProduct.id))) == 0
    setting = await test_session.get(FxRateSetting, 1)
    assert setting is not None
    assert setting.usd_to_uzs_rate is None


@pytest.mark.asyncio
async def test_unchanged_offer_price_does_not_add_history_or_refresh_staleness(
    test_session: AsyncSession,
) -> None:
    original_updated_at = datetime(2020, 1, 2, tzinfo=UTC)
    offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Boards",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("1250.50"),
        price_per_base_unit=Decimal("1250.5000"),
        currency="UZS",
        source_currency="UZS",
        source_price_per_pack=Decimal("1250.5000"),
        fx_rate_used=Decimal("1"),
        fx_rate_revision=0,
        staleness_state="stale",
        stock_qty=Decimal("6"),
        updated_at=original_updated_at,
    )
    test_session.add(offer)
    await test_session.flush()
    test_session.add(
        PriceHistory(
            shop_product_id=offer.id,
            price_per_pack=offer.price_per_pack,
            price_per_base_unit=offer.price_per_base_unit,
        )
    )
    await test_session.flush()

    await FxPricingService(test_session).set_offer_price(
        offer,
        amount=Decimal("1250.50"),
        currency="UZS",
        base_unit_code="dona",
    )

    assert (
        await test_session.scalar(
            select(func.count(PriceHistory.id)).where(PriceHistory.shop_product_id == offer.id)
        )
        == 1
    )
    assert offer.updated_at == original_updated_at
    assert offer.staleness_state == "stale"
    assert offer.stock_qty == Decimal("6")


@pytest.mark.asyncio
async def test_rate_publish_reprices_usd_offer_and_tier_without_refreshing_offer_staleness(
    test_session: AsyncSession,
) -> None:
    original_updated_at = datetime(2020, 1, 2, tzinfo=UTC)
    setting = FxRateSetting(
        id=1,
        usd_to_uzs_rate=Decimal("1.000000"),
        revision=5,
        updated_at=original_updated_at,
        updated_by=7,
    )
    offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Boards",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("4.80"),
        price_per_base_unit=Decimal("4.8000"),
        source_currency="USD",
        source_price_per_pack=Decimal("4.8000"),
        fx_rate_used=Decimal("1.000000"),
        fx_rate_revision=5,
        currency="UZS",
        staleness_state="stale",
        stock_qty=Decimal("17"),
        is_active=False,
        moderation_status="pending",
        updated_at=original_updated_at,
    )
    legacy_uzs_offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Legacy UZS",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("1250.00"),
        price_per_base_unit=Decimal("1250.0000"),
        source_currency="UZS",
        source_price_per_pack=Decimal("1250.0000"),
        fx_rate_used=Decimal("1.000000"),
        fx_rate_revision=0,
        updated_at=original_updated_at,
    )
    tier = ShopProductPriceTier(
        shop_product_id=1,
        min_qty=Decimal("20"),
        price_per_pack=Decimal("4.00"),
        source_currency="USD",
        source_price_per_pack=Decimal("4.0000"),
        fx_rate_used=Decimal("1.000000"),
        fx_rate_revision=5,
        updated_at=original_updated_at,
    )
    test_session.add_all([setting, offer, tier, legacy_uzs_offer])
    await test_session.flush()

    snapshot = await FxPricingService(test_session).publish_rate(
        Decimal("2.000000"), admin_id=42, expected_revision=5
    )

    assert snapshot.rate == Decimal("2.000000")
    assert snapshot.revision == 6
    assert snapshot.updated_by == 42
    assert offer.price_per_pack == Decimal("9.60")
    assert offer.price_per_base_unit == Decimal("9.6000")
    assert offer.source_price_per_pack == Decimal("4.8000")
    assert offer.fx_rate_used == Decimal("2.000000")
    assert offer.fx_rate_revision == 6
    assert offer.updated_at == original_updated_at
    assert offer.staleness_state == "stale"
    assert offer.stock_qty == Decimal("17")
    assert offer.is_active is False
    assert offer.moderation_status == "pending"
    assert tier.price_per_pack == Decimal("8.00")
    assert tier.source_price_per_pack == Decimal("4.0000")
    assert tier.fx_rate_used == Decimal("2.000000")
    assert tier.fx_rate_revision == 6
    assert tier.updated_at == original_updated_at
    assert legacy_uzs_offer.price_per_pack == Decimal("1250.00")
    assert legacy_uzs_offer.source_currency == "UZS"
    assert legacy_uzs_offer.fx_rate_revision == 0
    assert (
        await test_session.scalar(
            select(func.count(PriceHistory.id)).where(PriceHistory.shop_product_id == offer.id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_rate_publish_preflight_keeps_all_prices_and_revision_when_one_conversion_overflows(
    test_session: AsyncSession,
) -> None:
    setting = FxRateSetting(id=1, usd_to_uzs_rate=Decimal("1"), revision=2)
    valid_offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Valid",
        raw_unit="dona",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("4.80"),
        price_per_base_unit=Decimal("4.8000"),
        source_currency="USD",
        source_price_per_pack=Decimal("4.8000"),
        fx_rate_used=Decimal("1"),
        fx_rate_revision=2,
    )
    overflowing_offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Overflow",
        raw_unit="dona",
        pack_size=Decimal("1000"),
        pack_unit_code="dona",
        price_per_pack=Decimal("999999999999.00"),
        price_per_base_unit=Decimal("999999999.9990"),
        source_currency="USD",
        source_price_per_pack=Decimal("999999999999.0000"),
        fx_rate_used=Decimal("1"),
        fx_rate_revision=2,
    )
    test_session.add_all([setting, valid_offer, overflowing_offer])
    await test_session.flush()

    with pytest.raises(FxPricingError, match="amount_out_of_range"):
        await FxPricingService(test_session).publish_rate(
            Decimal("2"), admin_id=42, expected_revision=2
        )

    assert setting.usd_to_uzs_rate == Decimal("1.000000")
    assert setting.revision == 2
    assert valid_offer.price_per_pack == Decimal("4.80")
    assert valid_offer.fx_rate_revision == 2
    assert overflowing_offer.price_per_pack == Decimal("999999999999.00")
    assert await test_session.scalar(select(func.count(PriceHistory.id))) == 0


@pytest.mark.asyncio
async def test_rate_publish_preflight_keeps_all_prices_when_an_offer_unit_is_invalid(
    test_session: AsyncSession,
) -> None:
    setting = FxRateSetting(id=1, usd_to_uzs_rate=Decimal("1"), revision=2)
    offer = ShopProduct(
        shop_id=1,
        canonical_id=None,
        raw_name="Unknown unit",
        raw_unit="mystery",
        pack_size=Decimal("1"),
        pack_unit_code="mystery",
        price_per_pack=Decimal("4.80"),
        price_per_base_unit=Decimal("4.8000"),
        source_currency="USD",
        source_price_per_pack=Decimal("4.8000"),
        fx_rate_used=Decimal("1"),
        fx_rate_revision=2,
    )
    test_session.add_all([setting, offer])
    await test_session.flush()

    with pytest.raises(FxPricingError, match="invalid_unit"):
        await FxPricingService(test_session).publish_rate(
            Decimal("2"), admin_id=42, expected_revision=2
        )

    assert setting.usd_to_uzs_rate == Decimal("1.000000")
    assert setting.revision == 2
    assert offer.price_per_pack == Decimal("4.80")
    assert offer.fx_rate_revision == 2
    assert await test_session.scalar(select(func.count(PriceHistory.id))) == 0
