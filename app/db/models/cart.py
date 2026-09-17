"""The customer's live cart, separate from immutable ordered baskets."""

from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Cart(Base, TimestampMixin):
    __tablename__ = "carts"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class CartItem(Base):
    __tablename__ = "cart_items"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("carts.user_id", ondelete="CASCADE"), primary_key=True
    )
    canonical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), primary_key=True
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (CheckConstraint("qty > 0", name="positive_qty"),)


class CartMerge(Base):
    __tablename__ = "cart_merges"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("carts.user_id", ondelete="CASCADE"), primary_key=True
    )
    merge_key: Mapped[str] = mapped_column(String(160), primary_key=True)


class CheckoutAttempt(Base):
    __tablename__ = "checkout_attempts"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False)
