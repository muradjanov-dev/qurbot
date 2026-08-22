from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.common import (
    callback_reregister_cancel,
    callback_reregister_confirm,
    callback_set_district,
    callback_set_lang,
    callback_settings_back,
    callback_settings_language,
    callback_settings_reregister,
    cmd_reregister,
    menu_settings,
)
from app.bot.states import RegistrationStates
from app.db.models.shop import District
from app.db.models.user import User, UserAddress
from app.db.repositories.address_repo import AddressRepository


@pytest.mark.asyncio
async def test_reregistration_flow_complete(test_session: AsyncSession) -> None:
    # 1. Create a user with existing district and saved address
    district1 = District(name_uz="Chilonzor", name_ru="Чиланзар")
    district2 = District(name_uz="Yunusobod", name_ru="Юнусабад")
    test_session.add_all([district1, district2])
    await test_session.flush()

    user = User(
        tg_id=123456789,
        username="tester",
        full_name="Test User",
        lang="uz_latn",
        district_id=district1.id,
        role="customer",
    )
    test_session.add(user)
    await test_session.flush()

    address = UserAddress(
        user_id=user.id,
        lat=Decimal("41.2858"),
        lng=Decimal("69.2035"),
        address_text="Eski manzil, 1-uy",
        district_id=district1.id,
        is_default=True,
    )
    test_session.add(address)
    await test_session.commit()

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=123456789, user_id=123456789)
    state = FSMContext(storage=storage, key=key)

    # 2. Open Settings menu
    msg = AsyncMock(spec=Message)
    msg.answer = AsyncMock()
    await menu_settings(msg, state, lang="uz_latn")
    msg.answer.assert_called_once()

    # 3. User clicks "🔄 0 dan qayta ro'yxatdan o'tish"
    cb_msg = AsyncMock(spec=Message)
    cb_msg.edit_text = AsyncMock()
    cb_msg.delete = AsyncMock()
    cb_msg.answer = AsyncMock()
    cb_rereg = AsyncMock(spec=CallbackQuery)
    cb_rereg.message = cb_msg
    cb_rereg.answer = AsyncMock()

    await callback_settings_reregister(cb_rereg, lang="uz_latn")
    cb_msg.edit_text.assert_called_once()
    assert "0 dan qayta ro'yxatdan o'tish" in cb_msg.edit_text.call_args[0][0]

    # 4. User confirms re-registration ("✅ Ha, qaytadan boshlash")
    cb_confirm = AsyncMock(spec=CallbackQuery)
    cb_confirm.message = cb_msg
    cb_confirm.answer = AsyncMock()

    await callback_reregister_confirm(
        callback=cb_confirm,
        state=state,
        user=user,
        session=test_session,
        lang="uz_latn",
    )

    # Verify user.district_id was reset to None and old addresses deleted
    assert user.district_id is None
    addr_repo = AddressRepository(test_session)
    remaining_addrs = await addr_repo.list_for_user(user.id)
    assert len(remaining_addrs) == 0

    # Verify state is waiting_for_language
    current_state = await state.get_state()
    assert current_state == RegistrationStates.waiting_for_language.state

    # 5. User chooses language (e.g. Russian)
    cb_lang_msg = AsyncMock(spec=Message)
    cb_lang_msg.delete = AsyncMock()
    cb_lang_msg.answer = AsyncMock()
    cb_set_lang = AsyncMock(spec=CallbackQuery)
    cb_set_lang.data = "set_lang:ru"
    cb_set_lang.message = cb_lang_msg
    cb_set_lang.answer = AsyncMock()

    await callback_set_lang(
        callback=cb_set_lang,
        state=state,
        user=user,
        session=test_session,
    )

    # Since user.district_id is None, it should now advance to waiting_for_location
    assert user.lang == "ru"
    new_state = await state.get_state()
    assert new_state == RegistrationStates.waiting_for_location.state
    cb_lang_msg.answer.assert_called_once()

    # 6. User chooses district manually in the fallback path
    cb_dist_msg = AsyncMock(spec=Message)
    cb_dist_msg.delete = AsyncMock()
    cb_dist_msg.answer = AsyncMock()
    cb_set_dist = AsyncMock(spec=CallbackQuery)
    cb_set_dist.data = f"set_district:{district2.id}"
    cb_set_dist.message = cb_dist_msg
    cb_set_dist.answer = AsyncMock()

    await callback_set_district(
        callback=cb_set_dist,
        state=state,
        user=user,
        session=test_session,
        lang="ru",
    )

    # Verify user finished registration with district2
    assert user.district_id == district2.id
    final_state = await state.get_state()
    assert final_state is None


@pytest.mark.asyncio
async def test_reregister_command_and_cancel(test_session: AsyncSession) -> None:
    user = User(
        tg_id=999888777,
        username="tester2",
        full_name="Tester Two",
        lang="uz_latn",
        district_id=1,
        role="customer",
    )
    test_session.add(user)
    await test_session.flush()

    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=999888777, user_id=999888777)
    state = FSMContext(storage=storage, key=key)

    msg = AsyncMock(spec=Message)
    msg.answer = AsyncMock()

    # User issues /reregister
    await cmd_reregister(msg, state, user, lang="uz_latn")
    msg.answer.assert_called_once()
    assert "0 dan qayta ro'yxatdan o'tish" in msg.answer.call_args[0][0]

    # User clicks Cancel
    cb_msg = AsyncMock(spec=Message)
    cb_msg.edit_text = AsyncMock()
    cb_cancel = AsyncMock(spec=CallbackQuery)
    cb_cancel.message = cb_msg
    cb_cancel.answer = AsyncMock()

    await callback_reregister_cancel(cb_cancel, user, lang="uz_latn")
    cb_msg.edit_text.assert_called_once()
    assert "Sozlamalar" in cb_msg.edit_text.call_args[0][0]
    # Verify user district was not touched
    assert user.district_id == 1


@pytest.mark.asyncio
async def test_settings_language_and_back_navigation() -> None:
    cb_msg = AsyncMock(spec=Message)
    cb_msg.edit_text = AsyncMock()
    cb = AsyncMock(spec=CallbackQuery)
    cb.message = cb_msg
    cb.answer = AsyncMock()

    # User clicks "🌐 Tilni o'zgartirish" in settings
    await callback_settings_language(cb, lang="uz_latn")
    cb_msg.edit_text.assert_called_once()
    assert "tilni tanlang" in cb_msg.edit_text.call_args[0][0].lower()

    # User clicks back
    cb_msg.edit_text.reset_mock()
    await callback_settings_back(cb, lang="uz_latn")
    cb_msg.edit_text.assert_called_once()
    assert "Sozlamalar" in cb_msg.edit_text.call_args[0][0]
