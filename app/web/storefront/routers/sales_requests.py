"""Owned manual enquiries and assigned-operator resolution."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation
from app.db.models.sales_request import SalesRequest
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.cart_service import CartConflict, InvalidCartItem
from app.services.conversation_service import ConversationConflict
from app.services.house_shop import is_admin
from app.services.sales_request_service import SalesRequestService, request_data
from app.web.storefront.deps import current_lang, render, require_api_user
from app.web.storefront.security import require_csrf
from app.web.storefront.visitor import limit_guest_order

router = APIRouter(tags=["sales_requests"])


class RequestIn(BaseModel):
    cart_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=120)
    contact_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(max_length=32)
    district_id: int = Field(gt=0)
    address_text: str = Field(min_length=5, max_length=500)


class ResolutionIn(BaseModel):
    outcome: Literal["agreed", "cancelled"]
    note: str = Field(min_length=1, max_length=2000)


@router.post("/api/sales-requests", dependencies=[Depends(require_csrf)])
async def create_request(
    body: RequestIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_api_user),
) -> dict[str, Any]:
    key = "web:" + body.idempotency_key
    existing = await session.scalar(
        select(SalesRequest.id).where(
            SalesRequest.user_id == user.id, SalesRequest.idempotency_key == key
        )
    )
    if existing is None:
        await limit_guest_order(request, user)
    try:
        row = await SalesRequestService(session).create(
            user,
            revision=body.cart_revision,
            key=key,
            name=body.contact_name,
            phone=body.phone,
            district_id=body.district_id,
            address=body.address_text,
            channel="web",
        )
        result = request_data(row)
        await session.commit()
        return {"ok": True, "request": result}
    except (CartConflict, InvalidCartItem) as exc:
        await session.rollback()
        raise HTTPException(
            409 if isinstance(exc, CartConflict) or exc.message == "idempotency_conflict" else 422,
            exc.message,
        ) from exc


@router.get("/api/sales-requests")
async def list_requests(
    session: AsyncSession = Depends(get_db_session), user: User = Depends(require_api_user)
) -> dict[str, Any]:
    rows = (
        await session.scalars(
            select(SalesRequest)
            .where(SalesRequest.user_id == user.id)
            .order_by(SalesRequest.id.desc())
            .limit(100)
        )
    ).all()
    return {"requests": [request_data(row) for row in rows]}


@router.get("/api/sales-requests/{request_id}")
async def get_request(
    request_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_api_user),
) -> dict[str, Any]:
    row = await session.get(SalesRequest, request_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "request_not_found")
    return request_data(row)


@router.get("/sales-requests")
async def request_history(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_api_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    data = await list_requests(session, user)
    return render(
        request, "sales_requests.html", user=user, lang=lang, sales_requests=data["requests"]
    )


@router.get("/api/chat/operator/{conversation_id}/sales-requests")
async def operator_requests(
    conversation_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_api_user),
) -> dict[str, Any]:
    if not is_admin(user):
        raise HTTPException(403, "admin_required")
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.status == "ai":
        raise HTTPException(404, "conversation_not_found")
    rows = (
        await session.scalars(
            select(SalesRequest)
            .where(SalesRequest.conversation_id == conversation_id)
            .order_by(SalesRequest.id.desc())
            .limit(100)
        )
    ).all()
    return {"requests": [request_data(row) for row in rows]}


@router.post(
    "/api/chat/operator/sales-requests/{request_id}/resolve", dependencies=[Depends(require_csrf)]
)
async def resolve_request(
    request_id: int,
    body: ResolutionIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_api_user),
) -> dict[str, Any]:
    try:
        row = await SalesRequestService(session).resolve(user, request_id, body.outcome, body.note)
        result = request_data(row)
        await session.commit()
        return {"ok": True, "request": result}
    except (PermissionError, ConversationConflict, LookupError, ValueError) as exc:
        await session.rollback()
        status = (
            403
            if isinstance(exc, PermissionError)
            else 404
            if isinstance(exc, LookupError)
            else 409
            if isinstance(exc, ConversationConflict)
            else 422
        )
        raise HTTPException(status, str(exc)) from exc
