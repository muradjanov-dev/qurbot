"""Claim an anonymous browser cart after a verified Telegram sign-in.

The anonymous owner is resolved exclusively from the signed guest cookie and
its unexpired ``VisitorSession`` row.  A claim holds both cart locks until the
caller commits, merges duplicate products by the shared cart rule (maximum
quantity), and clears the source only after the destination merge succeeds.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User, VisitorSession
from app.services.cart_service import CartService, InvalidCartItem


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


NO_GUEST_CART = GuestCartClaim("none")


async def claim_guest_cart(
    session: AsyncSession,
    user: User,
    guest_token: str | None,
) -> GuestCartClaim:
    """Merge the browser's valid guest cart into ``user``'s cart atomically.

    ``guest_token`` is a cookie value, never an owner id.  Invalid, expired, or
    already-consumed cookies are a no-op.  A conflict keeps both carts and
    returns ``review_required`` so the auth doorway can send the customer to
    the basket before checkout.
    """
    if (
        not settings.guest_sessions_enabled
        or user.tg_id is None
        or user.is_blocked
        or not isinstance(guest_token, str)
        or len(guest_token) != 43
    ):
        return NO_GUEST_CART

    token_hash = sha256(guest_token.encode()).hexdigest()
    visitor = await session.scalar(
        select(VisitorSession).where(VisitorSession.token_hash == token_hash).with_for_update()
    )
    now = datetime.now(UTC)
    if visitor is None or visitor.expires_at.replace(tzinfo=UTC) <= now:
        return NO_GUEST_CART

    guest = await session.scalar(select(User).where(User.id == visitor.user_id).with_for_update())
    # A visitor record must never be able to redirect one person's cart into
    # another Telegram account or into an already authenticated account.
    if guest is None or guest.tg_id is not None or guest.id == user.id:
        return NO_GUEST_CART

    # Cart locks serialize first-cart creation as well as ordinary updates.
    # Always acquire them in primary-key order to keep cross-account claims
    # from deadlocking each other.
    carts = {guest.id: CartService(session), user.id: CartService(session)}
    for owner_id in sorted(carts):
        await carts[owner_id].lock(owner_id)

    source = await carts[guest.id].get(guest.id)
    destination = await carts[user.id].get(user.id)
    if source.lines:
        try:
            await carts[user.id].merge(
                user.id,
                [
                    {
                        "canonical_id": line["canonical_id"],
                        "qty": line["qty"],
                        "unit_code": line["unit_code"],
                    }
                    for line in source.lines
                ],
                merge_key=f"guest-claim:{guest.id}",
                expected_revision=destination.revision,
            )
        except InvalidCartItem as exc:
            return GuestCartClaim("review_required", exc.message)

        # The target's merge receipt and the source clear share the caller's
        # transaction.  A failure before commit leaves the original cart
        # intact; a retry after commit sees the consumed visitor session.
        await carts[guest.id].clear(guest.id, expected_revision=source.revision)

    await session.delete(visitor)
    return GuestCartClaim("claimed")
