from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import PK_BIGINT, Base, TimestampMixin
from app.db.models.catalog import CanonicalProduct, Unit
from app.db.models.shop import Shop, ShopProduct
from app.db.models.user import User

JSONType = JSON().with_variant(JSONB, "postgresql")


class Basket(Base, TimestampMixin):
    __tablename__ = "baskets"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="parsing", nullable=False
    )  # parsing|awaiting_confirmation|confirmed|quoted|ordered|abandoned

    user: Mapped[User] = relationship("User", lazy="selectin")
    lines: Mapped[list["BasketLine"]] = relationship(
        "BasketLine", back_populates="basket", cascade="all, delete-orphan", lazy="selectin"
    )
    quotes: Mapped[list["Quote"]] = relationship(
        "Quote", back_populates="basket", cascade="all, delete-orphan", lazy="selectin"
    )


class BasketLine(Base, TimestampMixin):
    __tablename__ = "basket_lines"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    basket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("baskets.id"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_name: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit_code: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("units.code"), nullable=True
    )
    canonical_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=True, index=True
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    match_method: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # alias|trgm|vector|llm|manual
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    basket: Mapped[Basket] = relationship("Basket", back_populates="lines", lazy="selectin")
    canonical_product: Mapped[CanonicalProduct | None] = relationship(
        "CanonicalProduct", lazy="selectin"
    )
    unit: Mapped[Unit | None] = relationship("Unit", lazy="selectin")


class Quote(Base, TimestampMixin):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    basket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("baskets.id"), nullable=False, index=True
    )
    strategy: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # cheapest|fastest|single_shop|premium|balanced
    items_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    coverage_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    shop_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eta_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing_line_ids: Mapped[list[int]] = mapped_column(JSONType, default=list, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    basket: Mapped[Basket] = relationship("Basket", back_populates="quotes", lazy="selectin")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="quote", lazy="selectin")


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("quotes.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False
    )  # new|confirmed|partially_fulfilled|fulfilled|cancelled
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    grand_total_quoted: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    grand_total_final: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    quote: Mapped[Quote] = relationship("Quote", back_populates="orders", lazy="selectin")
    user: Mapped[User] = relationship("User", lazy="selectin")
    shop_parts: Mapped[list["OrderShopPart"]] = relationship(
        "OrderShopPart", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderShopPart(Base, TimestampMixin):
    __tablename__ = "order_shop_parts"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id"), nullable=False, index=True
    )
    shop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shops.id"), nullable=False, index=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    shop_response: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending|accepted|rejected|partial
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order] = relationship("Order", back_populates="shop_parts", lazy="selectin")
    shop: Mapped[Shop] = relationship("Shop", lazy="selectin")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order_shop_part", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    order_shop_part_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("order_shop_parts.id"), nullable=False, index=True
    )
    canonical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=False
    )
    shop_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("shop_products.id"), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(32), ForeignKey("units.code"), nullable=False)
    unit_price_quoted: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fulfilled_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    order_shop_part: Mapped[OrderShopPart] = relationship(
        "OrderShopPart", back_populates="items", lazy="selectin"
    )
    canonical_product: Mapped[CanonicalProduct] = relationship("CanonicalProduct", lazy="selectin")
    shop_product: Mapped[ShopProduct] = relationship("ShopProduct", lazy="selectin")
    unit: Mapped[Unit] = relationship("Unit", lazy="selectin")
