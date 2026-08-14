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
    LargeBinary,
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

    # ── Listing fields (owner-supplied via the upload wizard) ──────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Telegram photo handles: [{"file_id", "file_unique_id", "pos"}]. Kept as a
    # JSON column rather than a child relationship on purpose -- every other
    # ShopProduct relationship is lazy="selectin", so a related table would add
    # a SELECT to the hot quote path (get_active_offers_for_canonicals) and
    # break the "<= 3 statements per basket" budget in SPEC §13. The durable
    # copy of the bytes lives in product_photo_blobs, keyed by file_unique_id.
    photos: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    # NULL means "unknown / not tracked", which is what every imported and
    # seeded offer stays at. Deliberately NOT consulted by the optimizer yet:
    # quoting against finite stock changes the cost model and needs its own
    # tests, so this captures the data without altering existing quotes.
    stock_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    # What the owner said the product was, before matching. Advisory only --
    # the authoritative category is canonical_product.category_id.
    proposed_category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=True
    )
    # Gates whether owner-supplied media/description is shown to customers.
    # Never gates quoting: the price is real even when the photo is unreviewed,
    # so a pending listing still competes normally.
    moderation_status: Mapped[str] = mapped_column(
        String(32), default="approved", nullable=False
    )  # pending|approved|rejected

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


class ShopProductDraft(Base, TimestampMixin):
    """A listing the owner is still filling in, written after every wizard step.

    The wizard keeps nothing important in FSM state: each answer lands here
    first, so a restart, a Redis eviction or a dropped session costs the owner
    at most the question they were on. `visited_steps` records which optional
    questions have already been asked, which is what lets the draft be resumed
    without re-asking things the owner deliberately skipped.
    """

    __tablename__ = "shop_product_drafts"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id"), nullable=False, index=True
    )
    owner_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )  # draft|applied|discarded

    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pack_size: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    pack_unit_code: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("units.code"), nullable=True
    )
    price_per_pack: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    stock_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    photos: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    visited_steps: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)

    matched_canonical_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=True
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    applied_shop_product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shop_products.id"), nullable=True
    )

    shop: Mapped[Shop] = relationship("Shop", lazy="selectin")
    category: Mapped[Any | None] = relationship("Category", lazy="selectin")

    __table_args__ = (Index("ix_shop_product_drafts_owner_status", "owner_tg_id", "status"),)


class ProductPhotoBlob(Base):
    """The durable copy of an uploaded photo.

    Telegram `file_id` values are convenient but bot-scoped: rotating the bot
    token invalidates every one of them, and they are not fetchable from the
    admin panel without a round trip. The bytes are therefore stored here on
    receipt so an uploaded photo is never dependent on Telegram still serving
    it. Intentionally has no relationship back to ShopProduct -- nothing in the
    quote path should ever be able to load image bytes by accident.
    """

    __tablename__ = "product_photo_blobs"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    file_unique_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    shop_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shops.id"), nullable=True, index=True
    )
    mime_type: Mapped[str] = mapped_column(String(64), default="image/jpeg", nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
