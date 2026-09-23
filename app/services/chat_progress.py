"""Best-effort durable Telegram status edits, independent of AI answer delivery."""

from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import MESSAGES, t
from app.core.logging import get_logger
from app.db.models.conversation import Conversation, ConversationJob
from app.db.models.user import User
from app.db.session import async_session_factory

logger = get_logger(__name__)


def _phrase_count() -> int:
    """How many rotating phrases the catalogue actually carries."""
    count = 0
    while f"sales_progress_{count}" in MESSAGES:
        count += 1
    return count


# Derived once: adding a phrase to the catalogue lengthens the carousel with
# no second place to update.
PHRASE_COUNT = _phrase_count()

# Slot is only a change-detector for "has the visible text moved?", so it has
# to distinguish the same phase in the queued and running states. Multiplying
# leaves room for both and stays clear of the terminal value below.
_DONE_SLOT = 100


def resume_markup(lang: str) -> InlineKeyboardMarkup:
    """The way back to the assistant from an unclaimed handoff.

    Built here rather than imported from the handlers: this module is loaded by
    the worker, and reaching into `app.bot.handlers` from it would drag the
    whole dispatcher in behind it.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("web_chat_back_to_ai", lang=lang), callback_data="chat:resume_ai"
                )
            ]
        ]
    )


def progress(job: ConversationJob, lang: str, now: datetime) -> tuple[int, str, bool]:
    created = (
        job.created_at.replace(tzinfo=UTC) if job.created_at.tzinfo is None else job.created_at
    )
    age = max(0, int((now - created).total_seconds()))
    if job.status not in {"pending", "running"}:
        key = (
            "chat_waiting"
            if job.status in {"human", "cancelled"}
            else "web_chat_failed"
            if job.status == "failed"
            else "sales_progress_ready"
        )
        return _DONE_SLOT, t(key, lang=lang), False
    slow = age >= settings.chat_progress_slow_after_seconds
    # Offset by job ID so two customers waiting at the same moment do not read
    # the same line, and every phrase gets used across requests.
    phase = min(age // settings.chat_progress_rotate_seconds, PHRASE_COUNT - 1)
    copy = (
        t("sales_progress_slow", lang=lang)
        if slow
        else t(f"sales_progress_{(job.id + phase) % PHRASE_COUNT}", lang=lang)
    )
    state = t(
        "sales_progress_running" if job.status == "running" else "sales_progress_queued", lang=lang
    )
    slot = phase * 2 + (1 if job.status == "running" else 0)
    return slot, f"{state}\n{copy}", slow


async def acknowledge(message: Message, session: AsyncSession, job_id: int, lang: str) -> None:
    """Reserve before send: ambiguous Telegram failures must not send duplicate status messages."""
    try:
        reserved = await session.execute(
            update(ConversationJob)
            .where(ConversationJob.id == job_id, ConversationJob.progress_slot == -1)
            .values(progress_slot=-2)
            .returning(ConversationJob.id)
        )
        claimed = reserved.scalar_one_or_none()
        await session.commit()
        if claimed is None:
            return
        job = await session.get(ConversationJob, job_id, populate_existing=True)
        assert job is not None
        slot, text, _ = progress(job, lang, datetime.now(UTC))
        await session.commit()
        # A message filed to the operator queue means the conversation is not
        # with the assistant. Offer the way back here as well as at the moment
        # of handoff: someone already waiting only ever sees this reply, and
        # without the button their next message gets the same answer forever.
        markup = resume_markup(lang) if job.status == "human" else None
        if markup is not None:
            text = f"{text}\n{t('web_chat_waiting_hint', lang=lang)}"
        sent = await message.answer(text, parse_mode=None, reply_markup=markup)
        await session.execute(
            update(ConversationJob)
            .where(ConversationJob.id == job_id)
            .values(telegram_status_id=sent.message_id, progress_slot=slot)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("chat_progress_ack_failed", job_id=job_id)


async def update_chat_progress(ctx: dict[str, Any]) -> None:
    bot = ctx.get("bot")
    if bot is None or not settings.telegram_notifications_enabled:
        return
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        ids = list(
            (
                await session.scalars(
                    select(ConversationJob.id)
                    .where(
                        ConversationJob.telegram_status_id.is_not(None),
                        ConversationJob.progress_slot != _DONE_SLOT,
                        or_(
                            ConversationJob.progress_lease_until.is_(None),
                            ConversationJob.progress_lease_until < now,
                        ),
                    )
                    .order_by(ConversationJob.id)
                    .limit(50)
                )
            ).all()
        )
    for job_id in ids:
        async with async_session_factory() as session:
            claimed = (
                await session.execute(
                    update(ConversationJob)
                    .where(
                        ConversationJob.id == job_id,
                        or_(
                            ConversationJob.progress_lease_until.is_(None),
                            ConversationJob.progress_lease_until < now,
                        ),
                    )
                    .values(progress_lease_until=now + timedelta(seconds=30))
                    .returning(ConversationJob.id)
                )
            ).scalar_one_or_none()
            if claimed is None:
                await session.rollback()
                continue
            job = await session.get(ConversationJob, job_id)
            assert job is not None
            conversation = await session.get(Conversation, job.conversation_id)
            assert conversation is not None
            user = await session.get(User, conversation.user_id)
            assert user is not None
            slot, text, slow = progress(job, user.lang, now)
            tg_id, message_id, old_slot = user.tg_id, job.telegram_status_id, job.progress_slot
            await session.commit()
        if slot != old_slot and tg_id:
            markup = (
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=t("web_chat_operator", lang=user.lang),
                                callback_data="chat:operator",
                            )
                        ]
                    ]
                )
                if slow
                else None
            )
            try:
                await bot.edit_message_text(
                    chat_id=tg_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=None,
                    reply_markup=markup,
                )
            except Exception:
                # Deleted messages, throttling, network errors must never affect answers.
                logger.warning("chat_progress_edit_failed", job_id=job_id)
        async with async_session_factory() as session:
            await session.execute(
                update(ConversationJob)
                .where(ConversationJob.id == job_id)
                .values(
                    progress_slot=slot,
                    progress_lease_until=now
                    + timedelta(seconds=settings.chat_progress_rotate_seconds - 1),
                )
            )
            await session.commit()
