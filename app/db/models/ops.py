from datetime import date as date_
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
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
from app.db.models.catalog import CanonicalProduct, ProductAlias
from app.db.models.user import User

JSONType = JSON().with_variant(JSONB, "postgresql")


class UnmatchedQuery(Base, TimestampMixin):
    __tablename__ = "unmatched_queries"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, index=True
    )
    occurrences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    suggested_canonical_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False
    )  # new|reviewing|resolved|junk
    resolved_alias_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("product_aliases.id"), nullable=True
    )

    user: Mapped[User | None] = relationship("User", lazy="selectin")
    suggested_canonical: Mapped[CanonicalProduct | None] = relationship(
        "CanonicalProduct", lazy="selectin"
    )
    resolved_alias: Mapped[ProductAlias | None] = relationship("ProductAlias", lazy="selectin")


class LLMCall(Base, TimestampMixin):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0.000000"), nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    props: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    user: Mapped[User | None] = relationship("User", lazy="selectin")


class DailyMetrics(Base, TimestampMixin):
    __tablename__ = "daily_metrics"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    date: Mapped[date_] = mapped_column(Date, unique=True, nullable=False, index=True)
    gmv: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"), nullable=False)
    order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    basket_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    match_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    auto_match_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    avg_lines_per_basket: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("0.00"), nullable=False
    )
    quote_to_order_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    price_freshness_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00"), nullable=False
    )
    llm_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0.000000"), nullable=False
    )
    strategy_mix: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
