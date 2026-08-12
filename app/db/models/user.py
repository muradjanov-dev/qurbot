from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
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
