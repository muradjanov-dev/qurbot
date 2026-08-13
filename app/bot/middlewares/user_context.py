import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.middlewares._unwrap import unwrap_event
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository

logger = logging.getLogger("bot.user")


class UserContextMiddleware(BaseMiddleware):
    """User context middleware: loads or creates the User entity and checks block status."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        inner = unwrap_event(event)
        from_user = inner.from_user if inner else None

        if not from_user:
            return await handler(event, data)

        session: AsyncSession | None = data.get("session")
        if not session:
            return await handler(event, data)

        user_repo = UserRepository(session)
        user = await user_repo.get_by_tg_id(from_user.id)

        if not user:
            # Create user with default preferences
            user = User(
                tg_id=from_user.id,
                username=from_user.username,
                full_name=from_user.full_name or from_user.first_name,
                lang="uz_latn",
                role="customer",
                is_blocked=False,
            )
            session.add(user)
            await session.flush()

        if user.is_blocked:
            logger.warning("Blocked user %d attempted interaction", from_user.id)
            if isinstance(inner, Message):
                await inner.answer("Sizning profilingiz bloklangan.")
            elif isinstance(inner, CallbackQuery):
                await inner.answer("Sizning profilingiz bloklangan.", show_alert=True)
            return None

        data["user"] = user
        data["user_repo"] = user_repo
        data["lang"] = user.lang or "uz_latn"
        return await handler(event, data)
