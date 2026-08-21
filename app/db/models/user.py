from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import PK_BIGINT, Base, TimestampMixin
from app.db.models.shop import District


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # uz_latn|uz_cyrl|ru
    lang: Mapped[str] = mapped_column(String(16), default="uz_latn", nullable=False)
    district_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("districts.id"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(
        String(32), default="customer", nullable=False
    )  # customer|shop_owner|admin
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referral_source: Mapped[str | None] = mapped_column(String(100), nullable=True)

    district: Mapped[District | None] = relationship("District", lazy="selectin")


class UserAddress(Base, TimestampMixin):
    """A delivery place the customer has saved.

    Addresses are anchored on coordinates, not text. A typed street address in
    Tashkent frequently does not resolve to a findable place -- many buildings
    have no reliable number -- so the pin is what the courier actually uses and
    `address_text` is the human label confirmed by the customer on top of it.

    Customers keep several (home, site, office) and pick one at checkout, which
    is the whole point: the right address depends on where the delivery goes,
    not on where they registered.
    """

    __tablename__ = "user_addresses"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lat: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    lng: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    # What the customer confirmed, which may be the geocoder's suggestion or
    # their own correction of it. Their wording wins -- they know the place.
    address_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Derived from the pin, not asked for. Delivery rules are per district, so
    # this still has to be resolved, just never as a question.
    district_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("districts.id"), nullable=True, index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    district: Mapped[District | None] = relationship("District", lazy="selectin")

    __table_args__ = (Index("ix_user_addresses_user_default", "user_id", "is_default"),)
