"""Best-effort durable Telegram status edits, independent of AI answer delivery."""

from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.i18n import t
from app.core.logging import get_logger
from app.db.models.conversation import Conversation, ConversationJob
from app.db.models.user import User
from app.db.session import async_session_factory

logger = get_logger(__name__)


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
        return 100, t(key, lang=lang), False
    # Offset by job ID lets all seven approved phrases appear across requests.
    phase = min(age // 10, 6)
    copy = (
        t("sales_progress_slow", lang=lang)
        if age >= 60
        else t(f"sales_progress_{(job.id + phase) % 7}", lang=lang)
    )
    state = t(
        "sales_progress_running" if job.status == "running" else "sales_progress_queued", lang=lang
    )
    return phase + (10 if job.status == "running" else 0), f"{state}\n{copy}", age >= 60


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
        sent = await message.answer(text, parse_mode=None)
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
                        ConversationJob.progress_slot != 100,
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
                .values(progress_slot=slot, progress_lease_until=now + timedelta(seconds=5))
            )
            await session.commit()
