from datetime import datetime
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import PK_BIGINT, Base, TimestampMixin

JSONType = JSON().with_variant(JSONB, "postgresql")


class Unit(Base, TimestampMixin):
    __tablename__ = "units"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_uz: Mapped[str] = mapped_column(String(100), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # mass|count|area|volume|length
    base_code: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("units.code"), nullable=True
    )
    factor_to_base: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), default=Decimal("1.0"), nullable=False
    )

    base_unit: Mapped["Unit | None"] = relationship("Unit", remote_side=[code], lazy="selectin")


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name_uz: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(32), nullable=True)

    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side=[id], back_populates="children", lazy="selectin"
    )
    children: Mapped[list["Category"]] = relationship(
        "Category", back_populates="parent", cascade="all, delete-orphan", lazy="selectin"
    )
    canonical_products: Mapped[list["CanonicalProduct"]] = relationship(
        "CanonicalProduct", back_populates="category", lazy="selectin"
    )


class CanonicalProduct(Base, TimestampMixin):
    __tablename__ = "canonical_products"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name_uz: Mapped[str] = mapped_column(String(255), nullable=False)
    name_uz_cyrl: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id"), nullable=False, index=True
    )
    base_unit_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("units.code"), nullable=False
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    tier: Mapped[str] = mapped_column(
        String(32), default="standard", nullable=False
    )  # economy|standard|premium
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    search_doc: Mapped[str] = mapped_column(Text, nullable=False)

    category: Mapped[Category] = relationship(
        "Category", back_populates="canonical_products", lazy="selectin"
    )
    base_unit: Mapped[Unit] = relationship("Unit", lazy="selectin")
    aliases: Mapped[list["ProductAlias"]] = relationship(
        "ProductAlias",
        back_populates="canonical_product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_canonical_products_search_doc_trgm",
            "search_doc",
            postgresql_using="gin",
            postgresql_ops={"search_doc": "gin_trgm_ops"},
        ),
        Index(
            "ix_canonical_products_attributes_jsonb",
            "attributes",
            postgresql_using="gin",
            postgresql_ops={"attributes": "jsonb_path_ops"},
        ),
    )


class ProductAlias(Base, TimestampMixin):
    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(PK_BIGINT, primary_key=True, autoincrement=True)
    canonical_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("canonical_products.id"), nullable=False, index=True
    )
    alias_norm: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alias_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), default="seed", nullable=False
    )  # seed|shop|llm|admin|user
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("1.00"), nullable=False
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    canonical_product: Mapped[CanonicalProduct] = relationship(
        "CanonicalProduct", back_populates="aliases", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "canonical_id", "alias_norm", name="uq_product_aliases_canonical_alias_norm"
        ),
        Index(
            "ix_product_aliases_alias_norm_approved",
            "alias_norm",
            unique=True,
            postgresql_where=text("is_approved IS TRUE"),
        ),
    )
