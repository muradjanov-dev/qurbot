from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_tg_id(self, tg_id: int) -> User | None:
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert_user(
        self,
        tg_id: int,
        username: str | None = None,
        full_name: str | None = None,
        lang: str = "uz_latn",
        referral_source: str | None = None,
    ) -> User:
        now = datetime.now(UTC)
        user = await self.get_by_tg_id(tg_id)
        if user:
            if username is not None:
                user.username = username
            if full_name is not None:
                user.full_name = full_name
            user.last_active_at = now
            await self.session.flush()
            return user

        new_user = User(
            tg_id=tg_id,
            username=username,
            full_name=full_name,
            lang=lang,
            referral_source=referral_source,
            last_active_at=now,
        )
        self.session.add(new_user)
        await self.session.flush()
        return new_user

    async def update_last_active(self, user_id: int) -> None:
        now = datetime.now(UTC)
        stmt = update(User).where(User.id == user_id).values(last_active_at=now)
        await self.session.execute(stmt)
