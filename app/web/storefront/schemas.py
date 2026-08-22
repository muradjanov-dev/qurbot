"""Request bodies the browser sends to the storefront's JSON endpoints.

Shared rather than per-router because the basket travels through several of
them: it is parsed on one page, priced on another, and ordered from a third,
and all three must read it the same way.

What is absent matters as much as what is here: no prices, no totals, no shop
ids. The client says what it wants; the server decides what that costs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# A pasted list longer than this is not a basket; refusing it early keeps the
# parser and the LLM fallback off obviously bad input.
MAX_TEXT_CHARS = 4000


class BasketLineIn(BaseModel):
    """One basket line as the browser holds it."""

    line_no: int = 0
    canonical_id: int | None = None
    qty: str = "0"
    unit_code: str | None = None


class ParseIn(BaseModel):
    """A free-text list to parse and match."""

    text: str = Field(max_length=MAX_TEXT_CHARS)
    start_no: int = 0


class ProductLineIn(BaseModel):
    """A catalogue product being added to the basket at a chosen quantity."""

    canonical_id: int
    qty: str = "1"
    line_no: int = 1


class QuoteIn(BaseModel):
    """A basket to price, optionally narrowed to one strategy."""

    lines: list[BasketLineIn] = Field(default_factory=list)
    strategy: str | None = None


class OrderIn(BaseModel):
    """Everything needed to turn a chosen quote into an order."""

    lines: list[BasketLineIn] = Field(default_factory=list)
    strategy: str | None = None
    phone: str = ""
    comment: str | None = None
    address_id: int | None = None
    address_text: str | None = None
    lat: float | None = None
    lng: float | None = None
    # What the customer was looking at when they pressed confirm. Prices move;
    # this is how we notice and ask again instead of quietly charging more.
    expected_total: str | None = None


class WebAppLoginIn(BaseModel):
    """Telegram Mini App init data, presented for verification."""

    init_data: str
    next: str = "/"
