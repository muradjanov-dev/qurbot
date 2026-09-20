"""Authenticated shared chat API; all mutations require session CSRF."""

from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation, ConversationJob
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.conversation_service import ConversationConflict, ConversationService
from app.web.storefront.deps import require_api_user
from app.web.storefront.security import require_csrf
from app.web.storefront.visitor import ip_key, limit, limit_guest_message

router = APIRouter(prefix="/api/chat", tags=["chat"])


class MessageInput(BaseModel):
    request_id: str = Field(min_length=1, max_length=96)
    text: str = Field(min_length=1, max_length=4000)


async def service(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[ConversationService]:
    try:
        yield ConversationService(session)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ConversationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
async def history(
    after: int = Query(0, ge=0),
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return await chat.snapshot(user, after)


@router.post("/messages", status_code=202, dependencies=[Depends(require_csrf)])
async def send(
    body: MessageInput,
    request: Request,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    existing = await chat.session.scalar(
        select(ConversationJob.id)
        .join(Conversation)
        .where(Conversation.user_id == user.id, ConversationJob.request_id == body.request_id)
    )
    if existing is None:
        await limit_guest_message(request, user)
    return await chat.submit(user, body.text, body.request_id)


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: int,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return await chat.get_job(user, job_id)


@router.post("/handoff", dependencies=[Depends(require_csrf)])
async def handoff(
    request: Request,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    if user.tg_id is None:
        await limit(request, "handoff:" + ip_key(request), 20, 3600)
    return await chat.handoff(user)


@router.get("/operator")
async def operator_queue(
    after_id: int = Query(0, ge=0),
    scope: Literal["all", "waiting", "mine", "others"] = "all",
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    rows = await chat.queue(user, after_id, scope)
    return {"conversations": rows, "next_cursor": rows[-1]["id"] if len(rows) == 50 else None}


@router.get("/operator/{conversation_id}")
async def operator_history(
    conversation_id: int,
    after: int = Query(0, ge=0),
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    chat._admin(user)
    conversation = await chat.session.get(Conversation, conversation_id)
    if conversation is None or conversation.status == "ai":
        raise HTTPException(404, "conversation_not_found")
    return await chat.transcript(conversation, after)


class ReadInput(BaseModel):
    sequence: int = Field(ge=0)


@router.post("/operator/{conversation_id}/read", dependencies=[Depends(require_csrf)])
async def mark_read(
    conversation_id: int,
    body: ReadInput,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, bool]:
    await chat.mark_read(user, conversation_id, body.sequence)
    return {"ok": True}


@router.post("/operator/{conversation_id}/claim", dependencies=[Depends(require_csrf)])
async def claim(
    conversation_id: int,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return await chat.claim(user, conversation_id)


@router.post("/operator/{conversation_id}/messages", dependencies=[Depends(require_csrf)])
async def operator_reply(
    conversation_id: int,
    body: MessageInput,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return await chat.operator_reply(user, conversation_id, body.text, body.request_id)


@router.post("/operator/{conversation_id}/close", dependencies=[Depends(require_csrf)])
async def close(
    conversation_id: int,
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return await chat.close(user, conversation_id)
