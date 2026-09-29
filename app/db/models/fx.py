"""The singleton administrator-managed USD to UZS exchange-rate setting."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FxRateSetting(Base):
    __tablename__ = "fx_rate_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    usd_to_uzs_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    revision: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        CheckConstraint("id = 1", name="singleton_id"),
        CheckConstraint(
            "usd_to_uzs_rate IS NULL OR usd_to_uzs_rate > 0",
            name="positive_rate",
        ),
        CheckConstraint("revision >= 0", name="nonnegative_revision"),
    )
