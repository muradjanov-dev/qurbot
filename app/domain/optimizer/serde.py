"""Turning a solved quote into plain data, and back.

Pure: dicts of strings and numbers in, frozen dataclasses out. Money crosses
this boundary as a string, never a float -- a quote that survives a round trip
through JSON with its Decimals intact is the difference between an order total
that matches what the customer was shown and one that is off by a cent.

Used wherever a variant has to leave memory: stored in `quotes.payload` as the
immutable snapshot SPEC §4.3 asks for, and sent to the browser to render.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.domain.optimizer.models import (
    BasketItemQuery,
    LineAssignment,
    OptimizationStrategy,
    QuoteVariant,
    ShopQuoteGroup,
)


def serialize_line(line: LineAssignment) -> dict[str, Any]:
    return {
        "line_no": line.line_no,
        "canonical_id": line.canonical_id,
        "product_name": line.product_name,
        "shop_id": line.shop_id,
        "shop_name": line.shop_name,
        "offer_id": line.offer_id,
        "needed_qty": str(line.needed_qty),
        "needed_unit": line.needed_unit,
        "pack_size": str(line.pack_size),
        "pack_unit": line.pack_unit,
        "packs_needed": line.packs_needed,
        "billed_qty": str(line.billed_qty),
        "overage_qty": str(line.overage_qty),
        "unit_price_uzs": str(line.unit_price_uzs),
        "line_cost_uzs": str(line.line_cost_uzs),
    }


def deserialize_line(data: dict[str, Any]) -> LineAssignment:
    return LineAssignment(
        line_no=int(data["line_no"]),
        canonical_id=int(data["canonical_id"]),
        product_name=str(data["product_name"]),
        shop_id=int(data["shop_id"]),
        shop_name=str(data["shop_name"]),
        offer_id=int(data["offer_id"]),
        needed_qty=Decimal(str(data["needed_qty"])),
        needed_unit=str(data["needed_unit"]),
        pack_size=Decimal(str(data["pack_size"])),
        pack_unit=str(data["pack_unit"]),
        packs_needed=int(data["packs_needed"]),
        billed_qty=Decimal(str(data["billed_qty"])),
        overage_qty=Decimal(str(data["overage_qty"])),
        unit_price_uzs=Decimal(str(data["unit_price_uzs"])),
        line_cost_uzs=Decimal(str(data["line_cost_uzs"])),
    )


def serialize_group(group: ShopQuoteGroup) -> dict[str, Any]:
    return {
        "shop_id": group.shop_id,
        "shop_name": group.shop_name,
        "district_name": group.district_name,
        "distance_km": group.distance_km,
        "lines": [serialize_line(line) for line in group.lines],
        "subtotal_uzs": str(group.subtotal_uzs),
        "delivery_fee_uzs": str(group.delivery_fee_uzs),
        "is_free_delivery": group.is_free_delivery,
        "eta_hours": group.eta_hours,
        "trust_score": group.trust_score,
    }


def deserialize_group(data: dict[str, Any]) -> ShopQuoteGroup:
    return ShopQuoteGroup(
        shop_id=int(data["shop_id"]),
        shop_name=str(data["shop_name"]),
        district_name=data.get("district_name"),
        distance_km=data.get("distance_km"),
        lines=tuple(deserialize_line(line) for line in data["lines"]),
        subtotal_uzs=Decimal(str(data["subtotal_uzs"])),
        delivery_fee_uzs=Decimal(str(data["delivery_fee_uzs"])),
        is_free_delivery=bool(data["is_free_delivery"]),
        eta_hours=int(data["eta_hours"]),
        trust_score=float(data["trust_score"]),
    )


def _serialize_missing(item: BasketItemQuery) -> dict[str, Any]:
    return {
        "line_no": item.line_no,
        "canonical_id": item.canonical_id,
        "name_uz": item.name_uz,
        "needed_qty": str(item.needed_qty),
        "unit_code": item.unit_code,
    }


def _deserialize_missing(data: dict[str, Any]) -> BasketItemQuery:
    return BasketItemQuery(
        line_no=int(data["line_no"]),
        canonical_id=int(data["canonical_id"]),
        name_uz=str(data["name_uz"]),
        needed_qty=Decimal(str(data["needed_qty"])),
        unit_code=str(data["unit_code"]),
    )


def serialize_variant(variant: QuoteVariant) -> dict[str, Any]:
    """Render a variant as JSON-safe primitives."""
    return {
        "strategy_labels": [label.value for label in variant.strategy_labels],
        "shop_groups": [serialize_group(group) for group in variant.shop_groups],
        "items_total_uzs": str(variant.items_total_uzs),
        "delivery_total_uzs": str(variant.delivery_total_uzs),
        "grand_total_uzs": str(variant.grand_total_uzs),
        "coverage_pct": variant.coverage_pct,
        "covered_count": variant.covered_count,
        "total_count": variant.total_count,
        "missing_lines": [_serialize_missing(item) for item in variant.missing_lines],
        "savings_vs_worst_uzs": str(variant.savings_vs_worst_uzs),
        "savings_pct": variant.savings_pct,
        "max_eta_hours": variant.max_eta_hours,
        "composite_score": variant.composite_score,
    }


def deserialize_variant(data: dict[str, Any]) -> QuoteVariant:
    """Rebuild a variant from `serialize_variant` output."""
    return QuoteVariant(
        strategy_labels=tuple(
            OptimizationStrategy(label) for label in data.get("strategy_labels", [])
        ),
        shop_groups=tuple(deserialize_group(group) for group in data.get("shop_groups", [])),
        items_total_uzs=Decimal(str(data["items_total_uzs"])),
        delivery_total_uzs=Decimal(str(data["delivery_total_uzs"])),
        grand_total_uzs=Decimal(str(data["grand_total_uzs"])),
        coverage_pct=float(data["coverage_pct"]),
        covered_count=int(data["covered_count"]),
        total_count=int(data["total_count"]),
        missing_lines=tuple(_deserialize_missing(item) for item in data.get("missing_lines", [])),
        savings_vs_worst_uzs=Decimal(str(data["savings_vs_worst_uzs"])),
        savings_pct=float(data["savings_pct"]),
        max_eta_hours=int(data["max_eta_hours"]),
        composite_score=float(data.get("composite_score", 0.0)),
    )
