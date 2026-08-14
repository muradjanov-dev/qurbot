"""The shop panel's inline buttons must actually reach their handlers.

Each button delegates to the command handler that already implements it. Those
calls used to be positional, so inserting a parameter into a command handler's
signature silently shifted every later argument -- "Mahsulotlarim" started
failing with "missing 1 required positional argument: 'lang'" in production.

mypy cannot catch this: aiogram's router decorators return a callable typed
with `...`, which accepts any arguments. Calling the handlers is the only way
to know they still bind.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import (
    cb_shop_delivery,
    cb_shop_orders,
    cb_shop_products,
    menu_shop_portal,
)
from app.db.models import District, User
from app.db.repositories import ShopRepository


async def _owner_with_shop(session: AsyncSession) -> User:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()

    repo = ShopRepository(session)
    shop = await repo.create_shop("Ark buloq", "+998900000001", district.id, "Manzil")
    await repo.add_shop_owner(shop.id, tg_id=4242)

    user = User(tg_id=4242, full_name="Owner", lang="uz_latn", role="shop_owner")
    session.add(user)
    await session.flush()
    return user


def _fake_callback() -> CallbackQuery:
    msg = AsyncMock(spec=Message)
    msg.answer = AsyncMock()
    msg.chat = SimpleNamespace(id=1)
    msg.message_id = 1
    cb = AsyncMock(spec=CallbackQuery)
    cb.message = msg
    cb.answer = AsyncMock()
    return cb


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [cb_shop_products, cb_shop_delivery, cb_shop_orders])
async def test_shop_panel_buttons_bind_to_their_handlers(
    test_session: AsyncSession, handler
) -> None:
    user = await _owner_with_shop(test_session)
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=4242))
    callback = _fake_callback()

    # A binding error raises TypeError before any reply is attempted.
    await handler(callback=callback, user=user, session=test_session, state=state, lang="uz_latn")
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_shop_portal_opens_for_an_owner(test_session: AsyncSession) -> None:
    user = await _owner_with_shop(test_session)
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=4242))
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await menu_shop_portal(
        message=message, user=user, session=test_session, state=state, lang="uz_latn"
    )

    message.answer.assert_awaited()
    assert "Ark buloq" in message.answer.call_args[0][0]
