import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import DeleteMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.middlewares.telegram_cleanup import TelegramCleanupMiddleware
from app.bot.transient import transient_answer
from app.core.config import settings
from app.db.base import Base
from app.db.models.telegram_message import TelegramMessage
from app.db.models.user import User
from app.services.telegram_cleanup import (
    _cleanup_telegram_messages_impl,
    mark_transient_message_deleted,
    queue_transient_message,
    register_transient_message,
)

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


class FakeBot:
    def __init__(self, side_effect=None):
        self.delete_message = AsyncMock(side_effect=side_effect)


@pytest.mark.asyncio
async def test_cleanup_waits_until_exactly_24h_and_deletes_once(test_session):
    await register_transient_message(
        test_session,
        chat_id=101,
        message_id=5,
        message_type="ai_customer_inbound",
        sent_at=NOW,
    )
    await test_session.commit()
    row = await test_session.scalar(select(TelegramMessage))
    assert row is not None
    assert row.due_at.replace(tzinfo=UTC) == NOW + timedelta(hours=24)

    bot = FakeBot()
    before = await _cleanup_telegram_messages_impl(
        test_session, bot, now=NOW + timedelta(hours=23, minutes=59)
    )
    assert before == (0, 0, 0)
    bot.delete_message.assert_not_awaited()

    at_due = await _cleanup_telegram_messages_impl(test_session, bot, now=NOW + timedelta(hours=24))
    assert at_due == (1, 0, 0)
    assert row.status == "deleted"
    assert row.deleted_at.replace(tzinfo=UTC) == NOW + timedelta(hours=24)

    repeated = await _cleanup_telegram_messages_impl(
        test_session, bot, now=NOW + timedelta(hours=25)
    )
    assert repeated == (0, 0, 0)
    bot.delete_message.assert_awaited_once_with(chat_id=101, message_id=5)


@pytest.mark.asyncio
async def test_registration_is_idempotent_and_admins_are_excluded(test_session):
    chat_id = settings.admin_tg_ids[0]
    await register_transient_message(
        test_session,
        chat_id=chat_id,
        message_id=2,
        message_type="ai_customer_outbound",
        sent_at=NOW,
    )
    await register_transient_message(
        test_session,
        chat_id=101,
        message_id=7,
        message_type="ai_customer_outbound",
        sent_at=NOW,
    )
    await register_transient_message(
        test_session,
        chat_id=101,
        message_id=7,
        message_type="ai_customer_outbound",
        sent_at=NOW,
    )
    await test_session.commit()

    assert await test_session.scalar(select(func.count()).select_from(TelegramMessage)) == 1
    row = await test_session.scalar(select(TelegramMessage))
    assert row is not None and row.chat_id == 101


@pytest.mark.asyncio
async def test_concurrent_webhook_replay_registers_one_unique_row(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram-cleanup.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def replay_registration() -> None:
        async with maker() as session:
            await register_transient_message(
                session,
                chat_id=111,
                message_id=14,
                message_type="ai_customer_inbound",
                sent_at=NOW,
            )
            await session.commit()

    try:
        await asyncio.gather(replay_registration(), replay_registration())
        async with maker() as session:
            assert await session.scalar(select(func.count()).select_from(TelegramMessage)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_promoted_admin_chat_is_excluded_by_registry_role(test_session):
    test_session.add(
        User(tg_id=905, full_name="Admin", lang="uz_cyrl", role="admin", is_blocked=False)
    )
    await test_session.flush()
    await register_transient_message(
        test_session,
        chat_id=905,
        message_id=8,
        message_type="ai_customer_inbound",
        sent_at=NOW,
    )
    await test_session.commit()
    assert await test_session.scalar(select(func.count()).select_from(TelegramMessage)) == 0


@pytest.mark.asyncio
async def test_configured_super_admin_chat_is_excluded_even_without_user_row(
    test_session, monkeypatch
):
    monkeypatch.setattr(settings, "admin_tg_ids", [])
    monkeypatch.setattr(settings, "super_admin_tg_ids", [906])
    await register_transient_message(
        test_session,
        chat_id=906,
        message_id=4,
        message_type="ai_customer_inbound",
        sent_at=NOW,
    )
    await test_session.commit()
    assert await test_session.scalar(select(func.count()).select_from(TelegramMessage)) == 0


@pytest.mark.asyncio
async def test_protected_message_types_cannot_be_queued_or_registered(test_session):
    for protected_type in (
        "admin_message",
        "order_confirmation",
        "order_number",
        "order_status",
        "receipt_pdf",
    ):
        with pytest.raises(ValueError):
            await register_transient_message(
                test_session,
                chat_id=101,
                message_id=3,
                message_type=protected_type,
                sent_at=NOW,
            )

        with pytest.raises(ValueError):
            queue_transient_message(
                {},
                chat_id=101,
                message_id=3,
                message_type=protected_type,
                sent_at=NOW,
            )

    await test_session.commit()
    assert await test_session.scalar(select(func.count()).select_from(TelegramMessage)) == 0


@pytest.mark.asyncio
async def test_outbound_transient_is_registered_but_order_confirmation_is_protected(
    test_session,
):
    message = SimpleNamespace(
        chat=SimpleNamespace(type="private", id=107),
        answer=AsyncMock(return_value=SimpleNamespace(message_id=43, date=NOW)),
    )
    sent = await transient_answer(message, test_session, "Temporary AI response")
    assert sent.message_id == 43

    with pytest.raises(ValueError):
        await register_transient_message(
            test_session,
            chat_id=107,
            message_id=44,
            message_type="order_confirmation",
            sent_at=NOW,
        )
    await test_session.commit()
    row = await test_session.scalar(select(TelegramMessage))
    assert row is not None
    assert row.chat_id == 107
    assert row.message_id == 43
    assert row.message_type == "guided_sales_transient"


@pytest.mark.asyncio
async def test_outbound_transient_helper_ignores_group_messages(test_session):
    message = SimpleNamespace(
        chat=SimpleNamespace(type="group", id=-1001),
        answer=AsyncMock(return_value=SimpleNamespace(message_id=45, date=NOW)),
    )
    await transient_answer(message, test_session, "Group response")
    await test_session.commit()
    assert await test_session.scalar(select(func.count()).select_from(TelegramMessage)) == 0


@pytest.mark.asyncio
async def test_explicit_dispatcher_queue_is_persisted_in_the_handler_session(test_session):
    middleware = TelegramCleanupMiddleware()

    async def handler(_event, data):
        queue_transient_message(
            data,
            chat_id=108,
            message_id=46,
            message_type="ai_customer_status",
            sent_at=NOW,
        )
        return "handled"

    result = await middleware(
        handler,
        SimpleNamespace(),
        {"session": test_session},
    )
    assert result == "handled"
    await test_session.commit()
    row = await test_session.scalar(select(TelegramMessage))
    assert row is not None
    assert row.chat_id == 108 and row.message_id == 46


@pytest.mark.asyncio
async def test_registration_rejects_invalid_and_non_private_ids(test_session):
    for chat_id, message_id in ((-123, 1), (0, 1), (109, 0), (True, 1), (109, False)):
        with pytest.raises(ValueError):
            await register_transient_message(
                test_session,
                chat_id=chat_id,
                message_id=message_id,
                message_type="ai_customer_inbound",
                sent_at=NOW,
            )
    await test_session.commit()
    assert await test_session.scalar(select(func.count()).select_from(TelegramMessage)) == 0


@pytest.mark.asyncio
async def test_retry_survives_worker_restart_and_success_is_idempotent(test_session):
    await register_transient_message(
        test_session,
        chat_id=102,
        message_id=9,
        message_type="ai_customer_status",
        sent_at=NOW - timedelta(hours=24),
    )
    await test_session.commit()
    retry_error = TelegramRetryAfter(
        method=DeleteMessage(chat_id=102, message_id=9),
        message="Too many requests",
        retry_after=60,
    )
    first_bot = FakeBot(side_effect=retry_error)
    first_result = await _cleanup_telegram_messages_impl(test_session, first_bot, now=NOW)
    assert first_result == (0, 1, 0)

    row = await test_session.scalar(select(TelegramMessage))
    assert row is not None
    assert row.status == "retry"
    assert row.attempt_count == 1
    assert row.next_attempt_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=60)

    resumed_bot = FakeBot()
    early = await _cleanup_telegram_messages_impl(
        test_session, resumed_bot, now=NOW + timedelta(seconds=59)
    )
    assert early == (0, 0, 0)
    resumed = await _cleanup_telegram_messages_impl(
        test_session, resumed_bot, now=NOW + timedelta(seconds=60)
    )
    assert resumed == (1, 0, 0)
    assert row.status == "deleted"
    resumed_bot.delete_message.assert_awaited_once_with(chat_id=102, message_id=9)


@pytest.mark.asyncio
async def test_progress_message_can_be_marked_deleted_and_old_rows_expire(test_session):
    await register_transient_message(
        test_session,
        chat_id=103,
        message_id=11,
        message_type="ai_customer_status",
        sent_at=NOW - timedelta(hours=24),
    )
    await register_transient_message(
        test_session,
        chat_id=104,
        message_id=12,
        message_type="ai_customer_inbound",
        sent_at=NOW - timedelta(hours=48),
    )
    await test_session.commit()

    await mark_transient_message_deleted(test_session, chat_id=103, message_id=11, deleted_at=NOW)
    await test_session.commit()
    bot = FakeBot()
    result = await _cleanup_telegram_messages_impl(test_session, bot, now=NOW)
    assert result == (0, 0, 1)
    rows = list((await test_session.scalars(select(TelegramMessage))).all())
    states = {(row.chat_id, row.message_id): row.status for row in rows}
    assert states == {(103, 11): "deleted", (104, 12): "expired"}
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_protects_chat_promoted_after_registration(test_session):
    await register_transient_message(
        test_session,
        chat_id=110,
        message_id=13,
        message_type="ai_customer_inbound",
        sent_at=NOW - timedelta(hours=24),
    )
    test_session.add(User(tg_id=110, full_name="Promoted Admin", lang="uz_cyrl", role="admin"))
    await test_session.commit()

    bot = FakeBot()
    result = await _cleanup_telegram_messages_impl(test_session, bot, now=NOW)
    assert result == (0, 0, 1)
    row = await test_session.scalar(select(TelegramMessage))
    assert row is not None
    assert row.status == "protected"
    assert row.last_error == "admin_chat_protected"
    bot.delete_message.assert_not_awaited()
