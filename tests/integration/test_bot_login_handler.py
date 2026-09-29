from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TelegramUser

from app.bot.dispatcher import dispatcher
from app.bot.handlers import bot_login as bot_login_module
from app.bot.handlers.bot_login import decide_browser_login, start_browser_login
from app.core.config import settings
from app.db.models.user import User
from app.services.bot_login import State


@pytest.mark.asyncio
async def test_private_login_start_precedes_generic_start_and_preserves_fsm_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replies: list[tuple[str, object | None]] = []
    fallback_calls: list[str] = []
    monkeypatch.setattr(settings, "storefront_webapp_url", "https://shop.example.test/path")

    async def answer(self: Message, text: str, *args: object, **kwargs: object) -> Message:
        replies.append((text, kwargs.get("reply_markup")))
        return self

    monkeypatch.setattr(Message, "answer", answer)

    class FakeLoginService:
        async def claim(self, token: str, tg_id: int) -> State | None:
            assert token == "A" * 32
            assert tg_id == 42
            return State(
                status="claimed",
                code="012345",
                browser_label="Chrome <script>",
                next_path="/catalog",
                tg_id=42,
                expires_in=300,
            )

    @asynccontextmanager
    async def open_fake_service():
        yield FakeLoginService()

    monkeypatch.setattr(bot_login_module, "open_bot_login_service", open_fake_service)

    login_router = Router(name="login_test")
    login_router.message.register(
        start_browser_login,
        CommandStart(deep_link=True, magic=F.args.startswith("login_")),
    )
    common_router = Router(name="common_test")

    @common_router.message(CommandStart())
    async def generic_start(message: Message) -> None:
        fallback_calls.append("generic")
        await message.answer("generic start")

    storage = MemoryStorage()
    test_dispatcher = Dispatcher(storage=storage)
    test_dispatcher.include_router(login_router)
    test_dispatcher.include_router(common_router)
    bot = Bot(token="123456:TEST-TOKEN")
    user = User(tg_id=42, full_name="Browser user")
    key = StorageKey(bot_id=bot.id, chat_id=42, user_id=42)
    fsm = FSMContext(storage=storage, key=key)
    await fsm.set_state("registration.waiting_for_phone")
    telegram_user = TelegramUser(id=42, is_bot=False, first_name="Browser")
    update = Update(
        update_id=1,
        message=Message(
            message_id=7,
            date=datetime.now(UTC),
            chat=Chat(id=42, type=ChatType.PRIVATE),
            from_user=telegram_user,
            text=f"/start login_{'A' * 32}",
        ),
    )

    await test_dispatcher.feed_update(bot, update, user=user, lang="uz_latn")

    assert not fallback_calls
    assert len(replies) == 1
    assert "012345" in replies[0][0]
    assert "Chrome &lt;script&gt;" in replies[0][0]
    assert "<script>" not in replies[0][0]
    assert "shop.example.test" in replies[0][0]
    assert "/path" not in replies[0][0]
    assert await fsm.get_state() == "registration.waiting_for_phone"
    keyboard = replies[0][1]
    assert keyboard is not None
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callback_data == [f"web_login:approve:{'A' * 32}", f"web_login:deny:{'A' * 32}"]
    assert all(len(value.encode()) <= 64 for value in callback_data if value is not None)


def test_production_dispatcher_registers_login_before_webapp_and_common() -> None:
    names = [router.name for router in dispatcher.sub_routers]
    assert names.index("bot_login") < names.index("webapp_launch") < names.index("common")


@pytest.mark.asyncio
async def test_private_callback_uses_the_actual_sender_id_and_service_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "B" * 32
    decisions: list[tuple[str, int, bool]] = []
    edits: list[str] = []

    class FakeLoginService:
        async def decide(self, challenge: str, tg_id: int, approve: bool) -> bool:
            decisions.append((challenge, tg_id, approve))
            return True

    @asynccontextmanager
    async def open_fake_service():
        yield FakeLoginService()

    async def answer(self: CallbackQuery, *args: object, **kwargs: object) -> bool:
        return True

    async def edit_text(self: Message, text: str, *args: object, **kwargs: object) -> Message:
        edits.append(text)
        return self

    monkeypatch.setattr(bot_login_module, "open_bot_login_service", open_fake_service)
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    monkeypatch.setattr(Message, "edit_text", edit_text)
    telegram_user = TelegramUser(id=42, is_bot=False, first_name="Browser")
    message = Message(
        message_id=8,
        date=datetime.now(UTC),
        chat=Chat(id=42, type=ChatType.PRIVATE),
        from_user=telegram_user,
        text="login challenge",
    )
    callback = CallbackQuery(
        id="callback-1",
        from_user=telegram_user,
        chat_instance="private-42",
        message=message,
        data=f"web_login:approve:{token}",
    )

    await decide_browser_login(callback, User(tg_id=42, full_name="Browser user"), "uz_latn")

    assert decisions == [(token, 42, True)]
    assert edits == ["Kirish tasdiqlandi. Sayt ochiq turgan brauzer oynasiga qayting."]
