"""Manage the shared USD to UZS rate and materialized shop-price values."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, DecimalException
from typing import Any, cast

from sqlalchemy import inspect, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm.state import InstanceState

from app.core.exceptions import DomainException
from app.db.models.fx import FxRateSetting
from app.db.models.shop import PriceHistory, ShopProduct, ShopProductPriceTier
from app.domain.pricing.currency import (
    USD,
    UZS,
    CurrencyConversionError,
    convert_to_uzs,
    normalize_currency,
    validate_base_unit_price,
    validate_rate,
    validate_source_amount,
)
from app.domain.pricing.units import unit_price


@dataclass(frozen=True, slots=True)
class FxSnapshot:
    rate: Decimal | None
    revision: int
    updated_at: datetime | None
    updated_by: int | None


class FxPricingError(ValueError):
    """A currency price cannot be applied safely."""

    def __init__(self, code: str, *, status_code: int = 422) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class FxConflict(FxPricingError):
    """The administrator edited an exchange-rate revision that has changed."""

    def __init__(self) -> None:
        super().__init__("revision_conflict", status_code=409)


class FxPricingService:
    """Convert source prices to UZS and publish rate changes atomically.

    The caller owns the transaction. These helpers flush when they need row ids,
    but never commit, so a rate and all derived offer prices share one commit.
    """

    _SETTING_ID = 1

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(self, lock: bool = False) -> FxSnapshot:
        setting = await self._get_setting(lock_mode="share" if lock else None)
        if setting is None:
            return FxSnapshot(rate=None, revision=0, updated_at=None, updated_by=None)
        return self._snapshot(setting)

    async def publish_rate(
        self,
        rate: Decimal,
        admin_id: int,
        expected_revision: int | None = None,
    ) -> FxSnapshot:
        try:
            normalized_rate = validate_rate(rate)
        except CurrencyConversionError as exc:
            raise FxPricingError(exc.code) from exc

        setting = await self._get_setting(lock_mode="exclusive")
        assert setting is not None
        if expected_revision is not None and setting.revision != expected_revision:
            raise FxConflict()
        if setting.usd_to_uzs_rate == normalized_rate:
            return self._snapshot(setting)

        next_revision = setting.revision + 1
        offer_rows = (
            (
                await self.session.execute(
                    select(ShopProduct).where(ShopProduct.source_currency == USD)
                )
            )
            .scalars()
            .all()
        )
        tier_rows = (
            (
                await self.session.execute(
                    select(ShopProductPriceTier).where(ShopProductPriceTier.source_currency == USD)
                )
            )
            .scalars()
            .all()
        )

        # Preflight every derived value before changing the setting or any offer.
        # A caller may turn FxPricingError into a 422 response and still commit
        # its request session, so validation must leave the unit of work untouched.
        offer_prices: list[tuple[ShopProduct, Decimal, Decimal]] = []
        for offer in offer_rows:
            source_amount = offer.source_price_per_pack
            if source_amount is None:
                raise FxPricingError("missing_source_amount")
            try:
                price_per_pack = convert_to_uzs(
                    source_amount,
                    currency=USD,
                    usd_to_uzs_rate=normalized_rate,
                )
                base_unit = (
                    offer.canonical_product.base_unit_code
                    if offer.canonical_product is not None
                    else offer.pack_unit_code or offer.raw_unit
                )
                price_per_base = validate_base_unit_price(
                    unit_price(
                        price_per_pack,
                        offer.pack_size,
                        offer.pack_unit_code or offer.raw_unit,
                        base_unit,
                    )
                )
            except CurrencyConversionError as exc:
                raise FxPricingError(exc.code) from exc
            except DomainException as exc:
                raise FxPricingError("invalid_unit") from exc
            except DecimalException as exc:
                raise FxPricingError("amount_out_of_range") from exc
            offer_prices.append((offer, price_per_pack, price_per_base))

        tier_prices: list[tuple[ShopProductPriceTier, Decimal]] = []
        for tier in tier_rows:
            source_amount = tier.source_price_per_pack
            if source_amount is None:
                raise FxPricingError("missing_source_amount")
            try:
                price_per_pack = convert_to_uzs(
                    source_amount,
                    currency=USD,
                    usd_to_uzs_rate=normalized_rate,
                )
            except CurrencyConversionError as exc:
                raise FxPricingError(exc.code) from exc
            tier_prices.append((tier, price_per_pack))

        now = datetime.now(UTC)
        setting.usd_to_uzs_rate = normalized_rate
        setting.revision = next_revision
        setting.updated_at = now
        setting.updated_by = admin_id

        for offer, price_per_pack, price_per_base in offer_prices:
            # Explicitly writing the original updated_at prevents TimestampMixin's
            # onupdate hook from making an FX-only repricing look like a new source
            # price. Staleness, stock, status and moderation are untouched.
            recorded_at = offer.updated_at
            await self.session.execute(
                update(ShopProduct)
                .where(ShopProduct.id == offer.id)
                .values(
                    price_per_pack=price_per_pack,
                    price_per_base_unit=price_per_base,
                    fx_rate_used=normalized_rate,
                    fx_rate_revision=next_revision,
                    updated_at=recorded_at,
                )
                .execution_options(synchronize_session=False)
            )
            _set_committed_value(offer, "price_per_pack", price_per_pack)
            _set_committed_value(offer, "price_per_base_unit", price_per_base)
            _set_committed_value(offer, "fx_rate_used", normalized_rate)
            _set_committed_value(offer, "fx_rate_revision", next_revision)
            _set_committed_value(offer, "updated_at", recorded_at)
            self.session.add(
                PriceHistory(
                    shop_product_id=offer.id,
                    price_per_pack=price_per_pack,
                    price_per_base_unit=price_per_base,
                )
            )

        for tier, price_per_pack in tier_prices:
            recorded_at = tier.updated_at
            await self.session.execute(
                update(ShopProductPriceTier)
                .where(ShopProductPriceTier.id == tier.id)
                .values(
                    price_per_pack=price_per_pack,
                    fx_rate_used=normalized_rate,
                    fx_rate_revision=next_revision,
                    updated_at=recorded_at,
                )
                .execution_options(synchronize_session=False)
            )
            _set_committed_value(tier, "price_per_pack", price_per_pack)
            _set_committed_value(tier, "fx_rate_used", normalized_rate)
            _set_committed_value(tier, "fx_rate_revision", next_revision)
            _set_committed_value(tier, "updated_at", recorded_at)

        await self.session.flush()
        return self._snapshot(setting)

    async def set_offer_price(
        self,
        offer: ShopProduct,
        amount: Decimal,
        currency: str,
        base_unit_code: str,
        updated_by: str = "admin",
    ) -> Decimal:
        try:
            source_currency = normalize_currency(currency)
            source_amount = validate_source_amount(amount)
            snapshot = await self.snapshot(lock=True)
            price_per_pack = convert_to_uzs(
                source_amount,
                currency=source_currency,
                usd_to_uzs_rate=snapshot.rate,
            )
            price_per_base = validate_base_unit_price(
                unit_price(
                    price_per_pack,
                    offer.pack_size,
                    offer.pack_unit_code or offer.raw_unit,
                    base_unit_code,
                )
            )
        except CurrencyConversionError as exc:
            self._discard_pending(offer)
            raise FxPricingError(exc.code) from exc
        except DomainException as exc:
            self._discard_pending(offer)
            raise FxPricingError("invalid_unit") from exc
        except DecimalException as exc:
            self._discard_pending(offer)
            raise FxPricingError("amount_out_of_range") from exc

        rate_used = snapshot.rate if source_currency == USD else Decimal("1")
        rate_revision = snapshot.revision if source_currency == USD else 0
        if (
            offer.currency == UZS
            and offer.source_currency == source_currency
            and offer.source_price_per_pack == source_amount
            and offer.price_per_pack == price_per_pack
            and offer.price_per_base_unit == price_per_base
            and offer.fx_rate_used == rate_used
            and offer.fx_rate_revision == rate_revision
        ):
            return price_per_pack

        offer.currency = UZS
        offer.source_currency = source_currency
        offer.source_price_per_pack = source_amount
        offer.price_per_pack = price_per_pack
        offer.price_per_base_unit = price_per_base
        offer.fx_rate_used = rate_used
        offer.fx_rate_revision = rate_revision
        offer.updated_by = updated_by
        offer.updated_at = datetime.now(UTC)
        offer.staleness_state = "fresh"
        offer.stock_qty = None

        if inspect(offer).transient:
            self.session.add(offer)
        await self.session.flush()
        self.session.add(
            PriceHistory(
                shop_product_id=offer.id,
                price_per_pack=price_per_pack,
                price_per_base_unit=price_per_base,
            )
        )
        await self.session.flush()
        return price_per_pack

    async def set_tier_price(
        self,
        tier: ShopProductPriceTier,
        amount: Decimal,
        currency: str,
    ) -> Decimal:
        try:
            source_currency = normalize_currency(currency)
            source_amount = validate_source_amount(amount)
            snapshot = await self.snapshot(lock=True)
            price_per_pack = convert_to_uzs(
                source_amount,
                currency=source_currency,
                usd_to_uzs_rate=snapshot.rate,
            )
        except CurrencyConversionError as exc:
            self._discard_pending(tier)
            raise FxPricingError(exc.code) from exc

        rate_used = snapshot.rate if source_currency == USD else Decimal("1")
        rate_revision = snapshot.revision if source_currency == USD else 0
        if (
            tier.source_currency == source_currency
            and tier.source_price_per_pack == source_amount
            and tier.price_per_pack == price_per_pack
            and tier.fx_rate_used == rate_used
            and tier.fx_rate_revision == rate_revision
        ):
            return price_per_pack

        tier.source_currency = source_currency
        tier.source_price_per_pack = source_amount
        tier.price_per_pack = price_per_pack
        tier.fx_rate_used = rate_used
        tier.fx_rate_revision = rate_revision
        tier.updated_at = datetime.now(UTC)
        if inspect(tier).transient:
            self.session.add(tier)
        await self.session.flush()
        return price_per_pack

    async def _get_setting(self, *, lock_mode: str | None) -> FxRateSetting | None:
        stmt = select(FxRateSetting).where(FxRateSetting.id == self._SETTING_ID)
        if lock_mode == "share":
            stmt = stmt.with_for_update(read=True)
        elif lock_mode == "exclusive":
            stmt = stmt.with_for_update()
        stmt = stmt.execution_options(populate_existing=True)
        with self.session.no_autoflush:
            setting = await self.session.scalar(stmt)
        if setting is None and lock_mode is not None:
            values = {"id": self._SETTING_ID, "usd_to_uzs_rate": None, "revision": 0}
            dialect = self.session.get_bind().dialect.name
            with self.session.no_autoflush:
                if dialect == "postgresql":
                    await self.session.execute(
                        pg_insert(FxRateSetting)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                elif dialect == "sqlite":
                    await self.session.execute(
                        sqlite_insert(FxRateSetting)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=["id"])
                    )
                else:
                    self.session.add(FxRateSetting(**values))
                    await self.session.flush()

            stmt = select(FxRateSetting).where(FxRateSetting.id == self._SETTING_ID)
            if lock_mode == "share":
                stmt = stmt.with_for_update(read=True)
            else:
                stmt = stmt.with_for_update()
            with self.session.no_autoflush:
                setting = await self.session.scalar(stmt.execution_options(populate_existing=True))
        return setting

    def _discard_pending(self, value: ShopProduct | ShopProductPriceTier) -> None:
        state = cast(InstanceState[Any], inspect(value))
        if state.pending:
            self.session.expunge(value)

    @staticmethod
    def _snapshot(setting: FxRateSetting) -> FxSnapshot:
        return FxSnapshot(
            rate=setting.usd_to_uzs_rate,
            revision=setting.revision,
            updated_at=setting.updated_at,
            updated_by=setting.updated_by,
        )


def _set_committed_value(value: object, key: str, new_value: object) -> None:
    set_committed_value(value, key, new_value)  # type: ignore[no-untyped-call]
