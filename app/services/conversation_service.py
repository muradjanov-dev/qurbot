"""Shared chat orchestration. Transactions never span a model or Telegram call.

Register process_conversation as an arq function and process_conversation_jobs
as a recurring job. The database is the queue; Redis is only a wake-up hint.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.conversation import (
    Conversation,
    ConversationJob,
    ConversationMessage,
    ConversationNotification,
)
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.db.session import async_session_factory
from app.services.cart_service import CartService, InvalidCartItem
from app.services.house_shop import is_admin
from app.services.sales_agent import AgentCart, DbAgentTools, SalesAgent, agent_available

logger = get_logger(__name__)


class ConversationConflict(ValueError):
    """A request conflicts with a previous request or the current owner."""


def message_data(message: ConversationMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "sequence": message.sequence,
        "role": message.role,
        "channel": message.channel,
        "text": message.text,
        "cards": message.cards[:3],
        "created_at": message.created_at.isoformat(),
    }


def job_data(job: ConversationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "job_id": job.id,
        "conversation_id": job.conversation_id,
        "request_id": job.request_id,
        "status": job.status,
        "message_id": job.message_id,
        "response_id": job.response_id,
        "error": job.error,
    }


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, user: User) -> Conversation:
        conversation = await self.session.scalar(
            select(Conversation).where(Conversation.user_id == user.id)
        )
        if conversation is None:
            try:
                async with self.session.begin_nested():
                    conversation = Conversation(user_id=user.id)
                    self.session.add(conversation)
                    await self.session.flush()
            except IntegrityError:
                conversation = await self.session.scalar(
                    select(Conversation).where(Conversation.user_id == user.id)
                )
                if conversation is None:
                    raise
        return conversation

    async def _lock(self, conversation_id: int) -> Conversation:
        # UPDATE is also a write lock on SQLite, used in local tests.
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(next_sequence=Conversation.next_sequence)
        )
        conversation = await self.session.get(Conversation, conversation_id, populate_existing=True)
        if conversation is None:
            raise LookupError("conversation_not_found")
        return conversation

    async def _append(
        self,
        conversation: Conversation,
        role: str,
        text: str,
        channel: str,
        cards: list[dict[str, Any]] | None = None,
    ) -> ConversationMessage:
        conversation.next_sequence += 1
        message = ConversationMessage(
            conversation_id=conversation.id,
            sequence=conversation.next_sequence,
            role=role,
            text=text,
            channel=channel,
            cards=(cards or [])[:3],
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def snapshot(self, user: User, after: int = 0) -> dict[str, Any]:
        conversation = await self.get_or_create(user)
        return await self.transcript(conversation, after)

    async def transcript(self, conversation: Conversation, after: int = 0) -> dict[str, Any]:
        messages = (
            await self.session.scalars(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation.id,
                    ConversationMessage.sequence > after,
                )
                .order_by(ConversationMessage.sequence)
                .limit(getattr(settings, "conversation_history_limit", 100))
            )
        ).all()
        return {
            "id": conversation.id,
            "conversation_id": conversation.id,
            "status": conversation.status,
            "operator_id": conversation.operator_id,
            "messages": [message_data(message) for message in messages],
            "next_sequence": messages[-1].sequence if messages else after,
        }

    async def submit(
        self,
        user: User,
        text: str,
        request_id: str,
        channel: str = "web",
    ) -> dict[str, Any]:
        text = text.strip()
        if not text or len(text) > getattr(settings, "conversation_message_max_chars", 4000):
            raise ValueError("invalid_message")
        if not request_id or len(request_id) > 128 or channel not in {"web", "telegram"}:
            raise ValueError("invalid_request")
        conversation = await self._lock((await self.get_or_create(user)).id)
        existing = await self.session.scalar(
            select(ConversationJob).where(
                ConversationJob.conversation_id == conversation.id,
                ConversationJob.request_id == request_id,
            )
        )
        if existing is not None:
            original = await self.session.get(ConversationMessage, existing.message_id)
            if original is None or original.text != text or original.channel != channel:
                raise ConversationConflict("request_id_reused")
            return job_data(existing)
        pending = await self.session.scalar(
            select(func.count())
            .select_from(ConversationJob)
            .where(
                ConversationJob.conversation_id == conversation.id,
                ConversationJob.status.in_(["pending", "running"]),
            )
        )
        if (pending or 0) >= getattr(settings, "conversation_pending_limit", 5):
            raise ConversationConflict("too_many_pending_messages")
        message = await self._append(conversation, "user", text, channel)
        job = ConversationJob(
            conversation_id=conversation.id,
            message_id=message.id,
            request_id=request_id,
            status="pending" if conversation.status == "ai" else "human",
        )
        self.session.add(job)
        if conversation.status != "ai":
            await self._notify_admins(conversation, f"message:{message.id}", text)
        await self.session.flush()
        await OpsRepository(self.session).log_event(
            "chat_message_submitted",
            user_id=user.id,
            props={
                "conversation_id": conversation.id,
                "job_id": job.id,
                "channel": channel,
            },
        )
        return job_data(job)

    async def get_job(self, user: User, job_id: int) -> dict[str, Any]:
        job = await self.session.scalar(
            select(ConversationJob)
            .join(Conversation, Conversation.id == ConversationJob.conversation_id)
            .where(ConversationJob.id == job_id, Conversation.user_id == user.id)
        )
        if job is None:
            raise LookupError("job_not_found")
        result = job_data(job)
        response = (
            await self.session.get(ConversationMessage, job.response_id)
            if job.response_id
            else None
        )
        result["response"] = message_data(response) if response else None
        return result

    async def _notify_admins(self, conversation: Conversation, event: str, text: str) -> None:
        admins = (
            await self.session.scalars(
                select(User).where(
                    or_(User.role == "admin", User.tg_id.in_(settings.admin_tg_ids)),
                    User.is_blocked.is_(False),
                )
            )
        ).all()
        targets = {admin.tg_id for admin in admins}
        targets.update(settings.admin_tg_ids)
        for tg_id in targets:
            self.session.add(
                ConversationNotification(
                    event_key=event,
                    tg_id=tg_id,
                    conversation_id=conversation.id,
                    kind="operator",
                    text=f"#{conversation.id}\n{text}",
                )
            )

    async def handoff(self, user: User) -> dict[str, Any]:
        conversation = await self._lock((await self.get_or_create(user)).id)
        if conversation.status == "ai":
            conversation.status = "waiting"
            conversation.generation += 1
            conversation.lease_token = None
            conversation.lease_until = None
            await OpsRepository(self.session).log_event(
                "chat_handoff",
                user_id=user.id,
                props={
                    "conversation_id": conversation.id,
                },
            )
            await self.session.execute(
                update(ConversationNotification)
                .where(
                    ConversationNotification.conversation_id == conversation.id,
                    ConversationNotification.kind.in_(["ai", "checkout"]),
                    ConversationNotification.sent_at.is_(None),
                )
                .values(sent_at=datetime.now(UTC))
            )
            await self.session.execute(
                update(ConversationJob)
                .where(
                    ConversationJob.conversation_id == conversation.id,
                    ConversationJob.status.in_(["pending", "running"]),
                )
                .values(status="human")
            )
            await self._append(conversation, "system", t("chat_waiting", lang=user.lang), "web")
            await self._notify_admins(
                conversation,
                f"handoff:{conversation.id}:{conversation.generation}",
                t("chat_waiting", lang=user.lang),
            )
        return await self.transcript(conversation)

    def _admin(self, admin: User) -> None:
        if admin.is_blocked or not is_admin(admin):
            raise PermissionError("admin_required")

    async def queue(self, admin: User) -> list[dict[str, Any]]:
        self._admin(admin)
        rows = (
            await self.session.scalars(
                select(Conversation)
                .where(Conversation.status.in_(["waiting", "human"]))
                .order_by(Conversation.updated_at)
                .limit(100)
            )
        ).all()
        return [
            {
                "id": row.id,
                "user_id": row.user_id,
                "status": row.status,
                "operator_id": row.operator_id,
            }
            for row in rows
        ]

    async def claim(self, admin: User, conversation_id: int) -> dict[str, Any]:
        self._admin(admin)
        conversation = await self._lock(conversation_id)
        if conversation.status == "human" and conversation.operator_id == admin.id:
            return await self.transcript(conversation)
        if conversation.status != "waiting" or conversation.operator_id is not None:
            raise ConversationConflict("already_claimed")
        conversation.status = "human"
        conversation.operator_id = admin.id
        conversation.generation += 1
        user = await self.session.get(User, conversation.user_id)
        if user is not None:
            message = await self._append(
                conversation, "system", t("web_chat_assigned", lang=user.lang), "operator"
            )
            self.session.add(
                ConversationNotification(
                    event_key=f"claimed:{message.id}",
                    tg_id=user.tg_id,
                    conversation_id=conversation.id,
                    kind="customer",
                    text=message.text,
                )
            )
        await OpsRepository(self.session).log_event(
            "chat_claimed",
            user_id=admin.id,
            props={
                "conversation_id": conversation.id,
            },
        )
        return await self.transcript(conversation)

    async def operator_reply(
        self,
        admin: User,
        conversation_id: int,
        text: str,
        request_id: str,
    ) -> dict[str, Any]:
        self._admin(admin)
        conversation = await self._lock(conversation_id)
        if conversation.status != "human" or conversation.operator_id != admin.id:
            raise ConversationConflict("not_conversation_owner")
        if not text.strip() or len(text) > getattr(
            settings, "conversation_message_max_chars", 4000
        ):
            raise ValueError("invalid_message")
        if not request_id or len(request_id) > 96:
            raise ValueError("invalid_request")
        key = f"operator:{admin.id}:{request_id}"
        existing = await self.session.scalar(
            select(ConversationJob).where(
                ConversationJob.conversation_id == conversation_id,
                ConversationJob.request_id == key,
            )
        )
        if existing:
            message = await self.session.get(ConversationMessage, existing.message_id)
            if message is None or message.text != text.strip():
                raise ConversationConflict("request_id_reused")
            return message_data(message)
        message = await self._append(conversation, "operator", text.strip(), "operator")
        self.session.add(
            ConversationJob(
                conversation_id=conversation.id,
                message_id=message.id,
                request_id=key,
                status="completed",
                response_id=message.id,
            )
        )
        user = await self.session.get(User, conversation.user_id)
        if user is not None:
            self.session.add(
                ConversationNotification(
                    event_key=f"reply:{message.id}",
                    tg_id=user.tg_id,
                    conversation_id=conversation.id,
                    kind="customer",
                    text=message.text,
                )
            )
        return message_data(message)

    async def close(self, admin: User, conversation_id: int) -> dict[str, Any]:
        self._admin(admin)
        conversation = await self._lock(conversation_id)
        if conversation.status != "human" or conversation.operator_id != admin.id:
            raise ConversationConflict("not_conversation_owner")
        conversation.status = "ai"
        conversation.operator_id = None
        conversation.generation += 1
        user = await self.session.get(User, conversation.user_id)
        if user is not None:
            message = await self._append(
                conversation, "system", t("chat_closed", lang=user.lang), "operator"
            )
            self.session.add(
                ConversationNotification(
                    event_key=f"closed:{message.id}",
                    tg_id=user.tg_id,
                    conversation_id=conversation.id,
                    kind="customer",
                    text=message.text,
                )
            )
        return await self.transcript(conversation)


class DurableTools:
    """Open a short, fenced transaction for each tool, never for a model request."""

    def __init__(self, conversation_id: int, generation: int, token: str, job_id: int) -> None:
        self.conversation_id = conversation_id
        self.generation = generation
        self.token = token
        self.job_id = job_id
        self.call_index = 0
        self.cards: list[dict[str, Any]] = []

    async def run(self, name: str, args: dict[str, Any], cart: AgentCart) -> dict[str, Any]:
        async with async_session_factory() as session:
            service = ConversationService(session)
            conversation = await service._lock(self.conversation_id)
            if (
                conversation.status != "ai"
                or conversation.generation != self.generation
                or conversation.lease_token != self.token
            ):
                raise ConversationConflict("ai_stopped")
            user = await session.get(User, conversation.user_id)
            if user is None or user.is_blocked:
                raise ConversationConflict("user_unavailable")
            job = await session.get(ConversationJob, self.job_id)
            assert job is not None
            signature = hashlib.sha256(
                json.dumps([name, args], sort_keys=True).encode()
            ).hexdigest()
            receipts = list(job.tool_results)
            index = self.call_index
            self.call_index += 1
            if index < len(receipts):
                receipt = receipts[index]
                if receipt["signature"] != signature:
                    raise ConversationConflict("recovery_tool_mismatch")
                restored = AgentCart.from_dict(receipt["cart"])
                current = await CartService(session).get(user.id)
                committed = AgentCart.from_dict(receipts[-1]["cart"])
                if committed.revision != current.revision:
                    raise ConversationConflict("cart_changed_during_recovery")
                cart.basket, cart.quote, cart.order = (
                    restored.basket,
                    restored.quote,
                    restored.order,
                )
                cart.revision, cart.quote_revision = restored.revision, restored.quote_revision
                self.cards = receipt.get("cards", [])
                return dict(receipt["output"])
            shared = CartService(session)
            snapshot = await shared.get(user.id)
            if cart.revision != snapshot.revision:
                cart.quote = None
                cart.order = None
            cart.revision = snapshot.revision
            cart.basket = [
                {
                    "canonical_id": line["canonical_id"],
                    "name": line["canonical_name"],
                    "qty": line["qty"],
                    "unit_code": line["unit_code"],
                }
                for line in snapshot.lines
            ]
            output = await DbAgentTools(session, user).run(name, args, cart)
            if name == "set_basket_item" and "error" not in output:
                product_id = int(args["product_id"])
                line = next(
                    (line for line in cart.basket if line["canonical_id"] == product_id), None
                )
                try:
                    snapshot = await shared.set_item(
                        user.id,
                        product_id,
                        line["qty"] if line else "0",
                        expected_revision=snapshot.revision,
                        unit_code=str(line["unit_code"]) if line else None,
                    )
                except InvalidCartItem:
                    raise ConversationConflict("invalid_cart_item") from None
                cart.revision = snapshot.revision
            if name == "get_quote" and "error" not in output:
                cart.quote_revision = snapshot.revision
            if name == "search_products":
                self.cards = [
                    dict(product, reference=f"/product/{product['id']}")
                    for product in output.get("products", [])[:3]
                ]
            job.tool_results = [
                *receipts,
                {
                    "name": name,
                    "signature": signature,
                    "output": output,
                    "cart": cart.to_dict(),
                    "cards": self.cards,
                },
            ]
            conversation.agent_state = cart.to_dict()
            await OpsRepository(session).log_event(
                "chat_tool_completed",
                user_id=user.id,
                props={
                    "conversation_id": conversation.id,
                    "job_id": job.id,
                    "tool": name,
                    "tool_index": index,
                    "failed": "error" in output,
                },
            )
            if name in {"get_quote", "prepare_order"} and "error" not in output:
                await OpsRepository(session).log_event(
                    "chat_quote_prepared" if name == "get_quote" else "chat_order_prepared",
                    user_id=user.id,
                    props={"conversation_id": conversation.id, "job_id": job.id},
                )
            await session.commit()
            return output


class DurableAgent(SalesAgent):
    async def _has_budget(self) -> bool:
        async with async_session_factory() as session:
            self.session = session
            try:
                return await super()._has_budget()
            finally:
                self.session = None

    async def _record(self, text: str, response: Any, latency_ms: int) -> None:
        async with async_session_factory() as session:
            self.session = session
            try:
                await super()._record(text, response, latency_ms)
                await session.commit()
            finally:
                self.session = None


async def process_conversation(ctx: dict[str, Any], conversation_id: int) -> None:
    """Process one oldest request; cron recovers pending and expired leases."""
    now = datetime.now(UTC)
    token = str(uuid4())
    timeout = getattr(settings, "conversation_job_timeout_seconds", 180)
    async with async_session_factory() as session:
        claimed = await session.scalar(
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.status == "ai",
                or_(Conversation.lease_until.is_(None), Conversation.lease_until < now),
            )
            .values(lease_token=token, lease_until=now + timedelta(seconds=timeout + 30))
            .returning(Conversation.id)
        )
        if claimed is None:
            return
        conversation = await session.get(Conversation, conversation_id)
        assert conversation is not None
        job = await session.scalar(
            select(ConversationJob)
            .where(
                ConversationJob.conversation_id == conversation_id,
                ConversationJob.status.in_(["pending", "running"]),
            )
            .order_by(ConversationJob.id)
            .limit(1)
        )
        if job is None:
            conversation.lease_token = None
            conversation.lease_until = None
            await session.commit()
            return
        job.status = "running"
        user = await session.get(User, conversation.user_id)
        message = await session.get(ConversationMessage, job.message_id)
        assert user is not None and message is not None
        job_id, generation, lang = job.id, conversation.generation, user.lang
        text, channel, tg_id = message.text, message.channel, user.tg_id
        blocked = user.is_blocked
        cart = AgentCart.from_dict(conversation.agent_state)
        history = (
            await session.scalars(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.id != message.id,
                    ConversationMessage.role.in_(["user", "assistant", "operator"]),
                    # Later queued user messages must not leak into an earlier turn.
                    or_(
                        ConversationMessage.role != "user",
                        ConversationMessage.sequence < message.sequence,
                    ),
                )
                .order_by(ConversationMessage.sequence.desc())
                .limit(settings.agent_history_max_messages)
            )
        ).all()
        cart.history = [
            {"role": "user" if row.role == "user" else "assistant", "content": row.text}
            for row in reversed(history)
        ]
        await session.commit()

    tools = DurableTools(conversation_id, generation, token, job_id)
    reply: str | None = None
    error: str | None = None
    started = time.monotonic()
    try:
        if not blocked and agent_available():
            async with asyncio.timeout(timeout):
                agent = DurableAgent(None, tools)
                try:
                    reply = await agent.reply(text, lang, cart)
                    error = agent.last_error
                finally:
                    await agent.client.close()
    except Exception as exc:
        # No exception text or model content is exposed to customers.
        error = "timeout" if isinstance(exc, TimeoutError) else "tool_or_worker_error"
        logger.warning("conversation_agent_failed", conversation_id=conversation_id, cause=error)
    if not reply:
        reply = t("chat_ai_unavailable", lang=lang)
        error = error or "agent_unavailable"
        cart.quote = None
        cart.order = None

    async with async_session_factory() as session:
        service = ConversationService(session)
        conversation = await service._lock(conversation_id)
        job = await session.get(ConversationJob, job_id)
        assert job is not None
        if conversation.lease_token != token:
            return
        conversation.lease_token = None
        conversation.lease_until = None
        if conversation.status != "ai" or conversation.generation != generation or blocked:
            if job.status == "running":
                job.status = "cancelled"
        else:
            live_cart = await CartService(session).get(conversation.user_id)
            if cart.revision is not None and live_cart.revision != cart.revision:
                reply = t("chat_ai_unavailable", lang=lang)
                error = "cart_changed"
                cart.quote = None
                cart.order = None
            response = await service._append(
                conversation,
                "assistant",
                reply[: settings.agent_reply_max_chars],
                channel,
                tools.cards if error is None else [],
            )
            conversation.agent_state = cart.to_dict()
            job.status = "completed"
            job.error = error
            job.response_id = response.id
            if channel == "telegram":
                session.add(
                    ConversationNotification(
                        event_key=f"reply:{response.id}",
                        tg_id=tg_id,
                        conversation_id=conversation_id,
                        kind="checkout" if cart.order and cart.quote else "ai",
                        text=response.text,
                    )
                )
        await OpsRepository(session).log_event(
            "chat_job_finished",
            user_id=conversation.user_id,
            props={
                "conversation_id": conversation.id,
                "job_id": job.id,
                "status": job.status,
                "error": error,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "model": settings.agent_model,
            },
        )
        await session.commit()


async def deliver_conversation_notifications(ctx: dict[str, Any]) -> None:
    """At-least-once outbox delivery; Telegram has no idempotent send API."""
    if not getattr(settings, "telegram_notifications_enabled", True):
        return
    bot = ctx.get("bot")
    if bot is None:
        return
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        ids = list(
            (
                await session.scalars(
                    select(ConversationNotification.id)
                    .where(
                        ConversationNotification.sent_at.is_(None),
                        or_(
                            ConversationNotification.lease_until.is_(None),
                            ConversationNotification.lease_until < now,
                        ),
                    )
                    .order_by(ConversationNotification.id)
                    .limit(100)
                )
            ).all()
        )
    for notification_id in ids:
        token = str(uuid4())
        async with async_session_factory() as session:
            row = await session.scalar(
                update(ConversationNotification)
                .where(
                    ConversationNotification.id == notification_id,
                    ConversationNotification.sent_at.is_(None),
                    or_(
                        ConversationNotification.lease_until.is_(None),
                        ConversationNotification.lease_until < now,
                    ),
                )
                .values(lease_token=token, lease_until=now + timedelta(seconds=60))
                .returning(ConversationNotification)
            )
            if row is None:
                continue
            tg_id, text, kind, conversation_id = row.tg_id, row.text, row.kind, row.conversation_id
            await session.commit()
        try:
            markup = None
            if kind == "operator":
                from app.bot.handlers.operator import operator_keyboard

                markup = operator_keyboard(conversation_id)
            elif kind == "checkout":
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

                async with async_session_factory() as session:
                    response_id = int(row.event_key.split(":")[-1])
                    job_id = await session.scalar(
                        select(ConversationJob.id).where(
                            ConversationJob.response_id == response_id,
                        )
                    )
                    customer = await session.scalar(select(User).where(User.tg_id == tg_id))
                    lang = customer.lang if customer else "uz_latn"
                markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=t("order_confirm_question", lang=lang),
                                callback_data=f"chat:checkout:{job_id}",
                            )
                        ]
                    ]
                )
            elif kind == "ai":
                from app.bot.handlers.ai_chat import product_keyboard

                async with async_session_factory() as session:
                    response_id = int(row.event_key.split(":")[-1])
                    response = await session.get(ConversationMessage, response_id)
                    customer = await session.scalar(select(User).where(User.tg_id == tg_id))
                    if response is not None and customer is not None:
                        snapshot = await CartService(session).get(customer.id)
                        markup = product_keyboard(response, snapshot.revision, customer.lang)
                        if response.cards:
                            text = text[:2800]
                        for card in response.cards[:3]:
                            price = card.get("price_from_uzs")
                            label = (
                                f"{price} UZS / {card.get('unit', '')}"
                                if price is not None
                                else t("web_product_confirm_required", lang=customer.lang)
                            )
                            text += f"\n\n{str(card.get('name', ''))[:100]}\n{label}"
                        await session.commit()
            await bot.send_message(tg_id, text, parse_mode=None, reply_markup=markup)
        except TelegramAPIError:
            logger.warning("conversation_notification_failed", notification_id=notification_id)
            continue
        async with async_session_factory() as session:
            await session.execute(
                update(ConversationNotification)
                .where(
                    ConversationNotification.id == notification_id,
                    ConversationNotification.lease_token == token,
                )
                .values(sent_at=datetime.now(UTC), lease_until=None, lease_token=None)
            )
            await session.commit()


async def process_conversation_jobs(ctx: dict[str, Any]) -> None:
    await deliver_conversation_notifications(ctx)
    async with async_session_factory() as session:
        ids = list(
            (
                await session.scalars(
                    select(ConversationJob.conversation_id)
                    .where(
                        ConversationJob.status.in_(["pending", "running"]),
                    )
                    .distinct()
                    .limit(100)
                )
            ).all()
        )
    # Independent conversations progress concurrently; each has a DB lease.
    await asyncio.gather(*(process_conversation(ctx, conversation_id) for conversation_id in ids))
