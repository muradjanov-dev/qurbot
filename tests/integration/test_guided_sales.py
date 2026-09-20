"""155-unit editing and status restart/failure scenarios; no Telegram or AI calls."""
# ruff: noqa: F811

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import Chat, Message

from app.bot.handlers.guided_sales import GuidedStates, add_quantity, custom_quantity, navigate
from app.db.models.conversation import ConversationJob
from app.db.models.user import User
from app.services import chat_progress
from app.services.cart_service import CartService
from app.services.conversation_service import ConversationService
from tests.integration.test_conversations import database  # noqa: F401
from tests.integration.test_unified_cart import seeded  # noqa: F401


@pytest.mark.parametrize("raw", ["155", "155,5", "-1", "0", "NaN", "1000001", "0.0000001", "hello"])
async def test_custom_quantity_is_deterministic_and_replaces_total(
    test_session, seeded, monkeypatch, raw
):
    user, product, _ = seeded
    state = FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=701, user_id=701))
    await state.set_state(GuidedStates.quantity)
    await state.update_data(guided_product=product.id, guided_revision=0)
    message = Message(
        message_id=10, date=datetime.now(UTC), chat=Chat(id=701, type="private"), text=raw
    )
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    monkeypatch.setattr(Message, "edit_reply_markup", AsyncMock())
    await custom_quantity(message, state, test_session, "uz_latn")
    assert not (await CartService(test_session).get(user.id)).lines
    if raw not in {"155", "155,5"}:
        assert await state.get_state() == GuidedStates.quantity.state
        assert (
            answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "g:cart"
        )
        return
    callback = SimpleNamespace(
        message=message,
        answer=AsyncMock(),
        data=answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data,
    )
    await add_quantity(callback, test_session, user, state, "uz_latn")
    cart = await CartService(test_session).get(user.id)
    assert cart.lines[0]["qty"] == raw.replace(",", ".")
    await add_quantity(
        callback, test_session, user, state, "uz_latn"
    )  # stale repeat cannot double it
    assert (await CartService(test_session).get(user.id)).lines[0]["qty"] == raw.replace(",", ".")
    for action in ["g:more", "g:back", "g:cart"]:
        callback.data = action
        await navigate(callback, state, test_session, user, "uz_latn")
        assert (await CartService(test_session).get(user.id)).lines


async def test_durable_progress_restart_terminal_and_edit_failure(database, monkeypatch):
    monkeypatch.setattr(chat_progress, "async_session_factory", database)
    monkeypatch.setattr(chat_progress.settings, "telegram_notifications_enabled", True)
    message = Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=11, type="private"))
    answer = AsyncMock(return_value=SimpleNamespace(message_id=99))
    monkeypatch.setattr(Message, "answer", answer)
    async with database() as session:
        result = await ConversationService(session).submit(
            await session.get(User, 1), "fanera", "status-one", "telegram"
        )
        await session.commit()
        await chat_progress.acknowledge(message, session, result["id"], "uz_latn")
        await chat_progress.acknowledge(message, session, result["id"], "uz_latn")
        assert answer.await_count == 1
        job = await session.get(ConversationJob, result["id"])
        assert job.telegram_status_id == 99
        job.created_at = datetime.now(UTC) - timedelta(seconds=65)
        job.status = "running"
        await session.commit()
    bot = SimpleNamespace(edit_message_text=AsyncMock())
    await chat_progress.update_chat_progress({"bot": bot})
    call = bot.edit_message_text.await_args.kwargs
    assert call["message_id"] == 99 and "AI javob" in call["text"]
    assert call["reply_markup"].inline_keyboard[0][0].callback_data == "chat:operator"
    async with database() as session:
        job = await session.get(ConversationJob, result["id"])
        job.status = "human"
        job.progress_lease_until = None
        await session.commit()
    bot.edit_message_text.side_effect = RuntimeError("Telegram unavailable")
    await chat_progress.update_chat_progress({"bot": bot})
    assert "AI javob" not in bot.edit_message_text.await_args.kwargs["text"]
    calls = bot.edit_message_text.await_count
    await chat_progress.update_chat_progress({"bot": bot})
    assert bot.edit_message_text.await_count == calls
    async with database() as session:
        assert (await session.get(ConversationJob, result["id"])).status == "human"


def test_all_seven_progress_phrases_and_terminal():
    now = datetime.now(UTC)
    texts = set()
    for job_id in range(7):
        job = ConversationJob(id=job_id, status="pending", created_at=now)
        texts.add(chat_progress.progress(job, "uz_latn", now)[1])
        assert chat_progress.progress(job, "ru", now + timedelta(seconds=60))[2]
        job.status = "completed"
        assert chat_progress.progress(job, "uz_cyrl", now)[0] == 100
    assert len(texts) == 7
