"""Pure assembly of a customer-facing product card.

Rendering is deliberately split in two: this module decides *what* a product
card contains and in what order, with no i18n, emoji or markup; the transport
layer (Telegram formatter today, a web catalog later) decides how it looks.
Keeping the decisions here means both surfaces show products consistently and
the logic stays unit-testable without a bot or a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.domain.listing.draft import PhotoRef


class StockDisplay(Enum):
    """What a customer should be told about availability."""

    IN_STOCK = "in_stock"
    LOW = "low"
    ON_ORDER = "on_order"
    OUT = "out"


@dataclass(frozen=True)
class ListingCard:
    """Everything needed to render one product, and nothing else."""

    title: str
    brand: str | None
    description: str | None
    shop_name: str | None
    pack_label: str
    price_per_pack: Decimal
    price_per_base_unit: Decimal
    base_unit: str
    stock: StockDisplay
    stock_qty: Decimal | None
    photos: tuple[PhotoRef, ...]
    attributes: tuple[tuple[str, str], ...]

    @property
    def has_photos(self) -> bool:
        return bool(self.photos)

    @property
    def primary_photo(self) -> PhotoRef | None:
        return self.photos[0] if self.photos else None


def ordered_photos(photos: tuple[PhotoRef, ...], max_photos: int) -> tuple[PhotoRef, ...]:
    """Deduplicated, position-ordered, capped.

    The owner uploads angles one at a time and may resend one; ordering by the
    recorded position (then by arrival) keeps the front shot first so the first
    thing a customer sees is the shot the owner led with.
    """
    seen: set[str] = set()
    unique: list[PhotoRef] = []
    for photo in sorted(enumerate(photos), key=lambda pair: (pair[1].pos, pair[0])):
        ref = photo[1]
        if ref.file_unique_id in seen:
            continue
        seen.add(ref.file_unique_id)
        unique.append(ref)
    return tuple(unique[:max_photos])


def stock_display(
    stock_status: str, stock_qty: Decimal | None, low_threshold: Decimal
) -> StockDisplay:
    """Collapse the raw status plus any counted quantity into one customer-facing state.

    A counted quantity beats the stored status when it contradicts it: a shop
    that says 'in stock' but recorded 0 left should not be shown as available.
    """
    if stock_qty is not None:
        if stock_qty <= 0:
            return StockDisplay.OUT
        if stock_qty <= low_threshold:
            return StockDisplay.LOW

    match stock_status:
        case "in_stock":
            return StockDisplay.IN_STOCK
        case "low":
            return StockDisplay.LOW
        case "on_order":
            return StockDisplay.ON_ORDER
        case _:
            return StockDisplay.OUT


def pack_label(pack_size: Decimal, pack_unit: str, base_unit: str) -> str:
    """A compact, human pack description: '50 kg', '1 dona', '10 litr'.

    Trailing zeros are stripped so a Decimal('50.0000') reads as '50', not
    '50.0000' -- the quantity is exact either way, this only affects display.
    Formatted with 'f' because normalize() turns 50.0000 into 5E+1, which would
    otherwise surface as scientific notation in front of a customer.
    """
    size_text = format(pack_size.normalize(), "f")
    unit = pack_unit or base_unit
    return f"{size_text} {unit}".strip()


def build_listing_card(
    *,
    title: str,
    price_per_pack: Decimal,
    price_per_base_unit: Decimal,
    pack_size: Decimal,
    pack_unit: str,
    base_unit: str,
    stock_status: str = "in_stock",
    stock_qty: Decimal | None = None,
    low_threshold: Decimal = Decimal("5"),
    brand: str | None = None,
    description: str | None = None,
    shop_name: str | None = None,
    photos: tuple[PhotoRef, ...] = (),
    max_photos: int = 3,
    attributes: dict[str, object] | None = None,
    show_photos: bool = True,
) -> ListingCard:
    """Assemble a card.

    `show_photos=False` is how unmoderated media is withheld: the product still
    renders and can still be bought, it simply carries no owner-supplied image
    until an admin has looked at it.
    """
    attr_pairs: tuple[tuple[str, str], ...] = ()
    if attributes:
        attr_pairs = tuple(
            (str(key), str(value))
            for key, value in sorted(attributes.items())
            if value is not None and str(value) != ""
        )

    return ListingCard(
        title=title.strip(),
        brand=brand,
        description=(description.strip() or None) if description else None,
        shop_name=shop_name,
        pack_label=pack_label(pack_size, pack_unit, base_unit),
        price_per_pack=price_per_pack,
        price_per_base_unit=price_per_base_unit,
        base_unit=base_unit,
        stock=stock_display(stock_status, stock_qty, low_threshold),
        stock_qty=stock_qty,
        photos=ordered_photos(photos, max_photos) if show_photos else (),
        attributes=attr_pairs,
    )
