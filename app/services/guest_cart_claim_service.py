"""Claim an anonymous browser cart after a verified Telegram sign-in.

The anonymous owner is resolved exclusively from the signed guest cookie and
its unexpired ``VisitorSession`` row.  A claim holds both cart locks until the
caller commits, merges duplicate products by the shared cart rule (maximum
quantity), and clears the source only after the destination merge succeeds.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User, VisitorSession
from app.services.cart_service import CartService, CartSnapshot, InvalidCartItem


@dataclass(frozen=True, slots=True)
class GuestCartClaim:
    status: str
    reason: str | None = None

    @property
    def claimed(self) -> bool:
        return self.status == "claimed"

    @property
    def needs_review(self) -> bool:
        return self.status == "review_required"


@dataclass(frozen=True, slots=True)
class GuestCartPreview:
    """Cookie-scoped cart snapshots shown while resolving a merge conflict."""

    source_lines: tuple[dict[str, Any], ...]
    account_lines: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _ClaimContext:
    visitor: VisitorSession
    guest_id: int
    guest_cart: CartService
    account_cart: CartService
    source: CartSnapshot
    destination: CartSnapshot


NO_GUEST_CART = GuestCartClaim("none")


async def _claim_context(
    session: AsyncSession,
    user: User,
    guest_token: str | None,
) -> _ClaimContext | None:
    """Resolve and lock only the guest cart named by a valid browser cookie."""
    if (
        not settings.guest_sessions_enabled
        or user.tg_id is None
        or user.is_blocked
        or not isinstance(guest_token, str)
        or len(guest_token) != 43
    ):
        return None

    token_hash = sha256(guest_token.encode()).hexdigest()
    visitor = await session.scalar(
        select(VisitorSession).where(VisitorSession.token_hash == token_hash).with_for_update()
    )
    now = datetime.now(UTC)
    if visitor is None:
        return None
    expires_at = visitor.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    else:
        expires_at = expires_at.astimezone(UTC)
    if expires_at <= now:
        return None

    guest = await session.scalar(select(User).where(User.id == visitor.user_id).with_for_update())
    # A visitor record must never be able to redirect one person's cart into
    # another authenticated account.
    if guest is None or guest.tg_id is not None or guest.id == user.id:
        return None

    # Cart locks serialize first-cart creation as well as ordinary updates.
    # Always acquire them in primary-key order to keep cross-account claims
    # from deadlocking each other.
    carts = {guest.id: CartService(session), user.id: CartService(session)}
    for owner_id in sorted(carts):
        await carts[owner_id].lock(owner_id)

    return _ClaimContext(
        visitor=visitor,
        guest_id=guest.id,
        guest_cart=carts[guest.id],
        account_cart=carts[user.id],
        source=await carts[guest.id].get(guest.id),
        destination=await carts[user.id].get(user.id),
    )


async def preview_guest_cart(
    session: AsyncSession,
    user: User,
    guest_token: str | None,
) -> GuestCartPreview | None:
    """Return guest and account lines only when the cookie proves ownership."""
    context = await _claim_context(session, user, guest_token)
    if context is None:
        return None
    return GuestCartPreview(
        source_lines=context.source.lines,
        account_lines=context.destination.lines,
    )


async def resolve_guest_cart_claim(
    session: AsyncSession,
    user: User,
    guest_token: str | None,
    *,
    drop_guest_ids: Sequence[int] = (),
    remove_account_ids: Sequence[int] = (),
) -> GuestCartClaim:
    """Resolve selected conflicts and merge both carts in the caller's transaction.

    ``guest_token`` is a cookie value, never an owner id.  Invalid, expired, or
    already-consumed cookies are a no-op. Selected IDs are checked against the
    cookie-owned source and signed-in destination. The complete proposed merge
    is validated before mutation; selected drops, destination removals, merge,
    source clear, and visitor consumption then commit or roll back together.
    """
    context = await _claim_context(session, user, guest_token)
    if context is None:
        return NO_GUEST_CART

    source_by_id = {int(line["canonical_id"]): line for line in context.source.lines}
    destination_by_id = {int(line["canonical_id"]): line for line in context.destination.lines}
    drop_ids = _selected_ids(drop_guest_ids)
    remove_ids = _selected_ids(remove_account_ids)
    if (
        drop_ids is None
        or remove_ids is None
        or not drop_ids.issubset(source_by_id)
        or not remove_ids.issubset(destination_by_id)
    ):
        return GuestCartClaim("invalid_selection", "guest_claim_selection_invalid")

    proposed = {
        product_id: dict(line)
        for product_id, line in destination_by_id.items()
        if product_id not in remove_ids
    }
    merge_lines: list[dict[str, Any]] = []
    try:
        for product_id, line in source_by_id.items():
            if product_id in drop_ids:
                continue
            qty, unit = await context.account_cart._validate(
                product_id, line["qty"], line["unit_code"]
            )
            existing = proposed.get(product_id)
            if existing is not None:
                if existing["unit_code"] != unit:
                    raise InvalidCartItem("unit_conflict")
                qty = max(qty, Decimal(str(existing["qty"])))
            merged_line = {"canonical_id": product_id, "qty": str(qty), "unit_code": unit}
            proposed[product_id] = merged_line
            merge_lines.append(merged_line)
        context.account_cart._check_size(len(proposed))
    except InvalidCartItem as exc:
        return GuestCartClaim("review_required", exc.message)

    destination = context.destination
    for product_id in sorted(remove_ids):
        destination = await context.account_cart.remove_item(
            user.id, product_id, expected_revision=destination.revision
        )

    if merge_lines:
        await context.account_cart.merge(
            user.id,
            merge_lines,
            merge_key=f"guest-claim:{context.guest_id}",
            expected_revision=destination.revision,
        )

    # Explicitly selected guest drops and all remaining guest lines are cleared
    # only in the same transaction that successfully merges the kept lines.
    await context.guest_cart.clear(context.guest_id, expected_revision=context.source.revision)
    await session.delete(context.visitor)
    return GuestCartClaim("claimed")


async def claim_guest_cart(
    session: AsyncSession,
    user: User,
    guest_token: str | None,
) -> GuestCartClaim:
    """Merge the complete guest cart using the shared max-quantity rule."""
    return await resolve_guest_cart_claim(session, user, guest_token)


def _selected_ids(values: Sequence[int]) -> set[int] | None:
    selected: set[int] = set()
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return None
        selected.add(value)
    return selected
