"""Atomic cart -> manual enquiry; never creates orders or stock movements."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import t
from app.db.models.catalog import CanonicalProduct
from app.db.models.order import Order
from app.db.models.sales_request import SalesRequest, SalesRequestItem
from app.db.models.shop import District
from app.db.models.user import User, UserAddress
from app.db.repositories.ops_repo import OpsRepository
from app.domain.normalize.phone import normalize_uz_phone
from app.services.cart_policy import assess_lines
from app.services.cart_service import CartConflict, CartService, InvalidCartItem
from app.services.conversation_service import ConversationConflict, ConversationService
from app.services.order_service import checkout_fingerprint


def request_data(row: SalesRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "status": row.status,
        "contact_name": row.contact_name,
        "phone": row.phone,
        "district_id": row.district_id,
        "district_name": row.district_name,
        "address": row.address,
        "created_at": row.created_at.isoformat(),
        "resolution_note": row.resolution_note,
        "items": [
            {
                "canonical_id": i.canonical_id,
                "name": i.name,
                "qty": format(i.qty.normalize(), "f"),
                "unit_code": i.unit_code,
                "attributes": i.attributes,
                "reference_unit_price": str(i.reference_unit_price)
                if i.reference_unit_price is not None
                else None,
                "requires_confirmation": i.requires_confirmation,
            }
            for i in row.items
        ],
    }


async def contact_defaults(session: AsyncSession, user: User) -> dict[str, Any]:
    request = await session.scalar(
        select(SalesRequest)
        .where(SalesRequest.user_id == user.id)
        .order_by(SalesRequest.id.desc())
        .limit(1)
    )
    order = await session.scalar(
        select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(1)
    )
    address = await session.scalar(
        select(UserAddress)
        .where(UserAddress.user_id == user.id)
        .order_by(UserAddress.is_default.desc(), UserAddress.id.desc())
        .limit(1)
    )
    return {
        "name": request.contact_name if request else user.full_name or "",
        "phone": request.phone if request else order.contact_phone if order else "",
        "district_id": request.district_id
        if request
        else address.district_id
        if address
        else user.district_id,
        "address": request.address if request else address.address_text if address else "",
    }


class SalesRequestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user: User,
        *,
        revision: int,
        key: str,
        name: str,
        phone: str,
        district_id: int,
        address: str,
        channel: str,
    ) -> SalesRequest:
        if not key or len(key) > 160 or channel not in {"web", "telegram"}:
            raise InvalidCartItem("invalid_request")
        fingerprint = checkout_fingerprint(
            {
                "revision": revision,
                "name": name.strip(),
                "phone": phone,
                "district": district_id,
                "address": address.strip(),
                "channel": channel,
            }
        )
        chat = ConversationService(self.session)
        # Shared lock order: conversation -> cart, as used by AI tools.
        conversation = await chat._lock((await chat.get_or_create(user)).id)
        cart = CartService(self.session)
        snapshot = await cart.get(user.id)
        old = await self.session.scalar(
            select(SalesRequest).where(
                SalesRequest.user_id == user.id, SalesRequest.idempotency_key == key
            )
        )
        if old:
            if old.fingerprint != fingerprint:
                raise InvalidCartItem("idempotency_conflict")
            return old
        if snapshot.revision != revision:
            raise CartConflict(snapshot.revision)
        normalized = normalize_uz_phone(phone)
        district = await self.session.get(District, district_id)
        if (
            not normalized
            or not name.strip()
            or len(name.strip()) > 100
            or not district
            or not 5 <= len(address.strip()) <= 500
        ):
            raise InvalidCartItem("invalid_contact")
        if not snapshot.lines:
            raise InvalidCartItem("empty_cart")
        lines = await assess_lines(self.session, snapshot.lines)
        row = SalesRequest(
            user_id=user.id,
            conversation_id=conversation.id,
            idempotency_key=key,
            fingerprint=fingerprint,
            channel=channel,
            status="open",
            contact_name=name.strip(),
            phone=normalized,
            district_id=district_id,
            district_name=f"{district.region}, "
            + (district.name_ru if user.lang == "ru" else district.name_uz),
            address=address.strip(),
            is_test=user.is_test or user.tg_id in settings.test_tg_ids,
            items=[],
        )
        for line in lines:
            await cart._validate(line["canonical_id"], line["qty"], line["unit_code"])
            product = await self.session.get(CanonicalProduct, line["canonical_id"])
            assert product is not None
            row.items.append(
                SalesRequestItem(
                    canonical_id=product.id,
                    name=product.name_ru if user.lang == "ru" else product.name_uz,
                    attributes=dict(product.attributes),
                    qty=Decimal(line["qty"]),
                    unit_code=line["unit_code"],
                    reference_unit_price=Decimal(line["reference_unit_price"])
                    if line["reference_unit_price"] is not None
                    and line["price_unit_code"] == line["unit_code"]
                    else None,
                    requires_confirmation=line["requires_confirmation"],
                )
            )
        self.session.add(row)
        await self.session.flush()
        await chat.handoff(user, channel=channel)
        await chat._append(
            conversation, "user", t("sales_request_sent", lang=user.lang, id=row.id), channel
        )
        await cart.clear(user.id, expected_revision=revision)
        await OpsRepository(self.session).log_event(
            "test_sales_request_created" if row.is_test else "sales_request_created",
            user_id=user.id,
            props={"request_id": row.id},
        )
        return row

    async def resolve(self, admin: User, request_id: int, outcome: str, note: str) -> SalesRequest:
        chat = ConversationService(self.session)
        chat._admin(admin)
        row = await self.session.get(SalesRequest, request_id)
        if row is None:
            raise LookupError("request_not_found")
        conversation = await chat._lock(row.conversation_id)
        await self.session.refresh(row)
        if conversation.status != "human" or conversation.operator_id != admin.id:
            raise ConversationConflict("not_conversation_owner")
        if outcome not in {"agreed", "cancelled"} or not 1 <= len(note.strip()) <= 2000:
            raise ValueError("invalid_resolution")
        if row.status != "open":
            if row.status == outcome and row.resolution_note == note.strip():
                return row
            raise ConversationConflict("already_resolved")
        row.status, row.resolution_note = outcome, note.strip()
        row.resolved_by, row.resolved_at = admin.id, datetime.now(UTC)
        customer = await self.session.get(User, row.user_id)
        assert customer is not None
        message = await chat._append(
            conversation,
            "system",
            f"#{row.id}: {t('sales_request_' + outcome, lang=customer.lang)}\n{note.strip()}",
            "operator",
        )
        chat._customer_notice(conversation, customer, message, "sales_request")
        await OpsRepository(self.session).log_event(
            "test_sales_request_resolved" if row.is_test else "sales_request_resolved",
            user_id=admin.id,
            props={"request_id": row.id, "outcome": outcome},
        )
        return row
