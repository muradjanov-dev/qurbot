"""Who may do what.

Admin rights are granted by Telegram id, and the grant itself is restricted to
super admins -- a promoted admin must not be able to promote further admins,
otherwise the restriction means nothing after the first grant.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import (
    admin_add_admin_id,
    cb_admin_add_admin,
    is_admin,
    is_super_admin,
    menu_admin_panel,
)
from app.db.models import User

SUPER_ID = 917456291


def _msg() -> Message:
    m = AsyncMock(spec=Message)
    m.answer = AsyncMock()
    m.chat = SimpleNamespace(id=1)
    return m


def _cb() -> CallbackQuery:
    cb = AsyncMock(spec=CallbackQuery)
    cb.message = _msg()
    cb.answer = AsyncMock()
    return cb


def _state(user_id: int) -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=user_id))


def _user(tg_id: int, role: str = "customer") -> User:
    return User(tg_id=tg_id, full_name="U", lang="uz_latn", role=role)


def test_role_predicates_separate_admin_from_super_admin() -> None:
    assert is_super_admin(_user(SUPER_ID)) is True
    assert is_admin(_user(SUPER_ID)) is True

    promoted = _user(555, role="admin")
    assert is_admin(promoted) is True
    assert is_super_admin(promoted) is False

    customer = _user(666)
    assert is_admin(customer) is False
    assert is_super_admin(customer) is False


@pytest.mark.asyncio
async def test_super_admin_promotes_by_telegram_id(test_session: AsyncSession) -> None:
    target = _user(4321)
    test_session.add(target)
    await test_session.flush()

    message = _msg()
    message.text = "4321"
    state = _state(SUPER_ID)
    await state.update_data({"dummy": 1})

    await admin_add_admin_id(
        message=message,
        user=_user(SUPER_ID),
        state=state,
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(target)
    assert target.role == "admin"


@pytest.mark.asyncio
async def test_a_promoted_admin_cannot_promote_others(test_session: AsyncSession) -> None:
    target = _user(4322)
    test_session.add(target)
    await test_session.flush()

    message = _msg()
    message.text = "4322"

    await admin_add_admin_id(
        message=message,
        user=_user(555, role="admin"),  # admin, but not super admin
        state=_state(555),
        session=test_session,
        lang="uz_latn",
    )

    await test_session.refresh(target)
    assert target.role == "customer"


@pytest.mark.asyncio
async def test_promotion_button_is_refused_for_non_super_admins() -> None:
    callback = _cb()
    await cb_admin_add_admin(
        callback=callback, user=_user(555, role="admin"), state=_state(555), lang="uz_latn"
    )
    # Refused with an alert, and no prompt was sent.
    callback.answer.assert_awaited()
    assert callback.answer.call_args.kwargs.get("show_alert") is True
    callback.message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_customers_cannot_open_the_admin_panel() -> None:
    message = _msg()
    await menu_admin_panel(message=message, user=_user(666), lang="uz_latn")

    message.answer.assert_awaited()
    assert "faqat adminlar" in message.answer.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_promoting_an_unknown_id_reports_instead_of_creating(
    test_session: AsyncSession,
) -> None:
    """A user must have started the bot first; we do not invent accounts."""
    message = _msg()
    message.text = "99999999"

    await admin_add_admin_id(
        message=message,
        user=_user(SUPER_ID),
        state=_state(SUPER_ID),
        session=test_session,
        lang="uz_latn",
    )

    assert "topilmadi" in message.answer.call_args[0][0].lower()
