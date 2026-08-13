from datetime import datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import PK_BIGINT, Base, TimestampMixin
from app.db.models.catalog import CanonicalProduct, Unit

JSONType = JSON().with_variant(JSONB, "postgresql")


class District(Base, TimestampMixin):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(100), default="Toshkent", nullable=False)
    name_uz: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    centroid_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    centroid_lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)

    shops: Mapped[list["Shop"]] = relationship("Shop", back_populates="district", lazy="selectin")


class Shop(Base, TimestampMixin):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    owner_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    district_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("districts.id"), nullable=False, index=True
    )
    address: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("5.00"), nullable=False)
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("1.00"), nullable=False
    )
    working_hours: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    payment_methods: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    district: Mapped[District] = relationship("District", back_populates="shops", lazy="selectin")
    delivery_rules: Mapped[list["ShopDeliveryRule"]] = relationship(
        "ShopDeliveryRule", back_populates="shop", cascade="all, delete-orphan", lazy="selectin"
    )
    products: Mapped[list["ShopProduct"]] = relationship(
        "ShopProduct", back_populates="shop", cascade="all, delete-orphan", lazy="selectin"
    )


class ShopDeliveryRule(Base, TimestampMixin):
    __tablename__ = "shop_delivery_rules"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id"), nullable=False, index=True
    )
    district_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("districts.id"), nullable=True, index=True
    )
    fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    free_above: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    min_order: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    eta_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    same_day_cutoff: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_pickup_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    shop: Mapped[Shop] = relationship("Shop", back_populates="delivery_rules", lazy="selectin")
    district: Mapped[District | None] = relationship("District", lazy="selectin")


class ShopProduct(Base, TimestampMixin):
    __tablename__ = "shop_products"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id"), nullable=False, index=True
    )
    canonical_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=True, index=True
    )
    raw_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    pack_size: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("1.0000"), nullable=False
    )
    pack_unit_code: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("units.code"), nullable=True
    )
    price_per_pack: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    price_per_base_unit: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", nullable=False)
    stock_status: Mapped[str] = mapped_column(
        String(32), default="in_stock", nullable=False
    )  # in_stock|low|on_order|out
    min_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("1.0000"), nullable=False
    )
    updated_by: Mapped[str] = mapped_column(
        String(32), default="shop", nullable=False
    )  # shop|admin|import
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    staleness_state: Mapped[str] = mapped_column(
        String(32), default="fresh", nullable=False
    )  # fresh|aging|stale

    shop: Mapped[Shop] = relationship("Shop", back_populates="products", lazy="selectin")
    canonical_product: Mapped[CanonicalProduct | None] = relationship(
        "CanonicalProduct", lazy="selectin"
    )
    pack_unit: Mapped[Unit | None] = relationship("Unit", lazy="selectin")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="shop_product", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "shop_id", "canonical_id", "pack_size", "pack_unit_code", name="uq_shop_products_offer"
        ),
        Index("ix_shop_products_updated_at", "updated_at"),
        # Covers the hot quote query (get_active_offers_for_canonicals): filters on
        # canonical_id IN (...) + is_active + staleness_state + stock_status, ordered
        # by (canonical_id, price_per_base_unit) -- the partial predicate matches the
        # WHERE clause and the trailing column satisfies the ORDER BY without a
        # separate sort step (Phase 9 hardening, SPEC §15).
        Index(
            "ix_shop_products_active_fresh",
            "canonical_id",
            "price_per_base_unit",
            postgresql_where=text(
                "is_active IS TRUE AND staleness_state <> 'stale' AND stock_status <> 'out'"
            ),
        ),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    shop_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_products.id"), nullable=False, index=True
    )
    price_per_pack: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    price_per_base_unit: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    shop_product: Mapped[ShopProduct] = relationship(
        "ShopProduct", back_populates="price_history", lazy="selectin"
    )


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="uploaded", nullable=False
    )  # uploaded|parsed|awaiting_confirmation|applied|failed
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    shop: Mapped[Shop] = relationship("Shop", lazy="selectin")
    rows: Mapped[list["ImportRow"]] = relationship(
        "ImportRow", back_populates="batch", cascade="all, delete-orphan", lazy="selectin"
    )


class ImportRow(Base, TimestampMixin):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id"), nullable=False, index=True
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    matched_canonical_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=True
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    resolution: Mapped[str] = mapped_column(
        String(32), default="auto", nullable=False
    )  # auto|manual|skipped
    applied_shop_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shop_products.id"), nullable=True
    )

    batch: Mapped[ImportBatch] = relationship("ImportBatch", back_populates="rows", lazy="selectin")
    matched_canonical: Mapped[CanonicalProduct | None] = relationship(
        "CanonicalProduct", lazy="selectin"
    )
