"""Unpriced enquiries are not orders and never enter fulfillment or revenue."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import PK_BIGINT, Base, TimestampMixin
from app.db.models.shop import JSONType


class SalesRequest(Base, TimestampMixin):
    __tablename__ = "sales_requests"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    fingerprint: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    contact_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(32))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    district_name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str] = mapped_column(Text)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["SalesRequestItem"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class SalesRequestItem(Base):
    __tablename__ = "sales_request_items"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("sales_requests.id"), index=True)
    canonical_id: Mapped[int] = mapped_column(ForeignKey("canonical_products.id"))
    name: Mapped[str] = mapped_column(String(500))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    unit_code: Mapped[str] = mapped_column(String(32))
    reference_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    requires_confirmation: Mapped[bool] = mapped_column(Boolean)
