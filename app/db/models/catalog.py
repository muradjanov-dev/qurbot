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
    # Where this row came from. Without it nothing distinguishes a product the
    # seed invented from one lifted off a real supplier's price list, which is
    # what an operator needs to know before trusting a price or deleting a row.
    source: Mapped[str] = mapped_column(
        String(32), default="seed", nullable=False, index=True
    )  # seed|supplier|admin|shop
    source_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The supplier's list price, kept apart from live shop offers: it is what
    # the catalogue is worth showing before any shop has uploaded anything.
    # NULL means the price list says "Kelishiladi" -- negotiable, not zero.
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    search_doc: Mapped[str] = mapped_column(Text, nullable=False)

    @property
    def display_image_url(self) -> str:
        """Return image_url or category-tailored Unsplash photo."""
        if self.image_url:
            return self.image_url
        if isinstance(self.attributes, dict) and self.attributes.get("image_url"):
            return str(self.attributes["image_url"])

        slug = self.category.slug if self.category else ""
        category_images = {
            "sement-va-qorishmalar": "https://images.unsplash.com/photo-1589939705384-5185137a7f0f?w=600&auto=format&fit=crop",
            "gisht-va-bloklar": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=600&auto=format&fit=crop",
            "metall-va-armatura": "https://images.unsplash.com/photo-1535813547-99c456a41d4a?w=600&auto=format&fit=crop",
            "yogoch": "https://images.unsplash.com/photo-1516253593875-bd7ba052fbc5?w=600&auto=format&fit=crop",
            "boyoq-va-lak": "https://images.unsplash.com/photo-1562259949-e8e7689d7828?w=600&auto=format&fit=crop",
            "plitka": "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?w=600&auto=format&fit=crop",
            "santexnika": "https://images.unsplash.com/photo-1585704032915-c3400ca199e7?w=600&auto=format&fit=crop",
            "elektr": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600&auto=format&fit=crop",
            "izolyatsiya": "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=600&auto=format&fit=crop",
            "tom-va-shifer": "https://images.unsplash.com/photo-1632759145351-1d592919f522?w=600&auto=format&fit=crop",
        }
        return category_images.get(
            slug,
            "https://images.unsplash.com/photo-1541888946425-d0fbb186a5b7?w=600&auto=format&fit=crop",
        )

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
