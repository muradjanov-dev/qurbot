"""Authenticated shared chat API; all mutations require session CSRF."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.conversation_service import ConversationConflict, ConversationService
from app.web.storefront.deps import require_api_user
from app.web.storefront.security import require_csrf

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
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
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
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return await chat.handoff(user)


@router.get("/operator")
async def operator_queue(
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    return {"conversations": await chat.queue(user)}


@router.get("/operator/{conversation_id}")
async def operator_history(
    conversation_id: int,
    after: int = Query(0, ge=0),
    user: User = Depends(require_api_user),
    chat: ConversationService = Depends(service),
) -> dict[str, Any]:
    chat._admin(user)
    conversation = await chat.session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(404, "conversation_not_found")
    return await chat.transcript(conversation, after)


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
