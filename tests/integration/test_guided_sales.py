"""155-unit editing and status restart/failure scenarios; no Telegram or AI calls."""
# ruff: noqa: F811

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import Chat, Message

from app.bot.handlers.guided_sales import (
    GuidedStates,
    add_quantity,
    custom_quantity,
    navigate,
    show_cart,
)
from app.core.config import settings
from app.core.i18n import t
from app.db.models.conversation import ConversationJob
from app.db.models.user import User
from app.services import chat_progress
from app.services.cart_service import CartService
from app.services.conversation_service import ConversationService
from tests.integration.test_conversations import database  # noqa: F401
from tests.integration.test_unified_cart import seeded  # noqa: F401


async def test_hundred_anchors_show_correct_cart_total(test_session, seeded, monkeypatch) -> None:
    user, product, offer = seeded
    product.name_uz = "Oq anker 10x112"
    offer.price_per_pack = offer.price_per_base_unit = Decimal("1135")
    await test_session.flush()
    await CartService(test_session).set_item(user.id, product.id, "100", expected_revision=0)
    message = Message(message_id=99, date=datetime.now(UTC), chat=Chat(id=701, type="private"))
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    await show_cart(message, test_session, user, "uz_latn")
    rendered = answer.await_args.args[0]
    assert "1.135 so'm / dona" in rendered
    assert "113.500 so'm" in rendered
    assert "1135.0000" not in rendered


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
    running_label = t("sales_progress_running", lang=settings.default_lang)
    assert call["message_id"] == 99 and running_label in call["text"]
    assert call["reply_markup"].inline_keyboard[0][0].callback_data == "chat:operator"
    async with database() as session:
        job = await session.get(ConversationJob, result["id"])
        job.status = "human"
        job.progress_lease_until = None
        await session.commit()
    bot.edit_message_text.side_effect = RuntimeError("Telegram unavailable")
    await chat_progress.update_chat_progress({"bot": bot})
    assert running_label not in bot.edit_message_text.await_args.kwargs["text"]
    calls = bot.edit_message_text.await_count
    await chat_progress.update_chat_progress({"bot": bot})
    assert bot.edit_message_text.await_count == calls
    async with database() as session:
        assert (await session.get(ConversationJob, result["id"])).status == "human"


def test_every_progress_phrase_is_reachable_and_terminal():
    now = datetime.now(UTC)
    count = chat_progress.PHRASE_COUNT
    assert count >= 20, "the carousel is meant to be long enough not to repeat"
    texts = set()
    for job_id in range(count):
        job = ConversationJob(id=job_id, status="pending", created_at=now)
        texts.add(chat_progress.progress(job, "uz_latn", now)[1])
        assert chat_progress.progress(job, "ru", now + timedelta(seconds=60))[2]
        job.status = "completed"
        assert chat_progress.progress(job, "uz_cyrl", now)[0] == chat_progress._DONE_SLOT
    assert len(texts) == count


def test_progress_text_rotates_every_configured_interval():
    """The visible line has to move, and its slot with it, or no edit is sent."""
    now = datetime.now(UTC)
    step = settings.chat_progress_rotate_seconds
    job = ConversationJob(id=0, status="pending", created_at=now)
    seen = [
        chat_progress.progress(job, "uz_cyrl", now + timedelta(seconds=step * n))
        for n in range(chat_progress.PHRASE_COUNT)
    ]
    slots = [slot for slot, _text, _slow in seen]
    assert len(set(slots)) == len(slots), "each interval must change the slot"
    assert len({text for _slot, text, _slow in seen}) == chat_progress.PHRASE_COUNT
    # One second in, nothing has moved yet.
    assert chat_progress.progress(job, "uz_cyrl", now + timedelta(seconds=1))[0] == slots[0]


def test_queued_and_running_never_share_a_slot():
    now = datetime.now(UTC)
    job = ConversationJob(id=0, status="pending", created_at=now)

    def slots() -> set[int]:
        return {
            chat_progress.progress(job, "ru", now + timedelta(seconds=3 * n))[0]
            for n in range(chat_progress.PHRASE_COUNT)
        }

    queued = slots()
    job.status = "running"
    running = slots()
    assert not queued & running
    assert chat_progress._DONE_SLOT not in queued | running


async def test_waiting_customer_is_offered_the_way_back_on_every_message(database, monkeypatch):
    """The escape hatch has to be where a stuck customer actually looks.

    Once an admin has claimed the conversation the assistant stands down, so
    every later message is filed to the operator queue. Without a button on
    that reply, an admin who claimed and went quiet holds the customer
    indefinitely.
    """
    monkeypatch.setattr(chat_progress, "async_session_factory", database)
    message = Message(message_id=1, date=datetime.now(UTC), chat=Chat(id=12, type="private"))
    answer = AsyncMock(return_value=SimpleNamespace(message_id=77))
    monkeypatch.setattr(Message, "answer", answer)

    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        await service.handoff(user, channel="telegram")
        # An admin takes it over; only then does the assistant stand down, and
        # only then does the customer need a way back.
        admin = User(tg_id=917456291, role="admin")
        session.add(admin)
        await session.flush()
        await service.claim(admin, (await service.get_or_create(user)).id)
        result = await service.submit(user, "g'isht kerak", "stuck-one", "telegram")
        await session.commit()
        assert result["status"] == "human"
        await chat_progress.acknowledge(message, session, result["id"], "uz_cyrl")

    markup = answer.await_args.kwargs["reply_markup"]
    assert markup is not None, "a waiting customer must be offered the way back"
    assert markup.inline_keyboard[0][0].callback_data == "chat:resume_ai"
    assert t("web_chat_waiting_hint", lang="uz_cyrl") in answer.await_args.args[0]


async def test_answered_message_carries_no_resume_button(database, monkeypatch):
    """The offer belongs to the operator queue, not to an ordinary AI reply."""
    monkeypatch.setattr(chat_progress, "async_session_factory", database)
    message = Message(message_id=2, date=datetime.now(UTC), chat=Chat(id=13, type="private"))
    answer = AsyncMock(return_value=SimpleNamespace(message_id=78))
    monkeypatch.setattr(Message, "answer", answer)

    async with database() as session:
        service = ConversationService(session)
        user = await session.get(User, 1)
        result = await service.submit(user, "fanera", "normal-one", "telegram")
        await session.commit()
        assert result["status"] == "pending"
        await chat_progress.acknowledge(message, session, result["id"], "uz_cyrl")

    assert answer.await_args.kwargs["reply_markup"] is None
