"""Saved delivery addresses."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.shop import District
from app.db.models.user import UserAddress
from app.domain.geo import GeoPoint


class AddressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user_id: int) -> Sequence[UserAddress]:
        """Saved places, default first, then most recently added."""
        stmt = (
            select(UserAddress)
            .where(UserAddress.user_id == user_id)
            .order_by(UserAddress.is_default.desc(), UserAddress.id.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get(self, address_id: int) -> UserAddress | None:
        return await self.session.get(UserAddress, address_id)

    async def get_default(self, user_id: int) -> UserAddress | None:
        stmt = (
            select(UserAddress)
            .where(UserAddress.user_id == user_id, UserAddress.is_default.is_(True))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def add(
        self,
        *,
        user_id: int,
        lat: Decimal,
        lng: Decimal,
        address_text: str,
        district_id: int | None,
        label: str | None = None,
        make_default: bool = False,
    ) -> UserAddress:
        """Save a place. The first one a customer saves is their default."""
        existing = await self.list_for_user(user_id)
        is_default = make_default or not existing
        if is_default:
            await self._clear_default(user_id)

        address = UserAddress(
            user_id=user_id,
            label=label,
            lat=lat,
            lng=lng,
            address_text=address_text,
            district_id=district_id,
            is_default=is_default,
        )
        self.session.add(address)
        await self.session.flush()
        return address

    async def set_default(self, user_id: int, address_id: int) -> UserAddress | None:
        address = await self.get(address_id)
        if address is None or address.user_id != user_id:
            return None
        await self._clear_default(user_id)
        address.is_default = True
        await self.session.flush()
        return address

    async def delete(self, user_id: int, address_id: int) -> bool:
        address = await self.get(address_id)
        if address is None or address.user_id != user_id:
            return False
        was_default = address.is_default
        await self.session.delete(address)
        await self.session.flush()
        if was_default:
            # Never leave a customer with saved addresses but no default --
            # checkout would then have nothing preselected.
            remaining = await self.list_for_user(user_id)
            if remaining:
                remaining[0].is_default = True
                await self.session.flush()
        return True

    async def delete_all_for_user(self, user_id: int) -> None:
        """Delete all saved delivery addresses for a user (e.g. on full re-registration)."""
        stmt = delete(UserAddress).where(UserAddress.user_id == user_id)
        await self.session.execute(stmt)
        await self.session.flush()

    async def _clear_default(self, user_id: int) -> None:
        stmt = (
            update(UserAddress)
            .where(UserAddress.user_id == user_id, UserAddress.is_default.is_(True))
            .values(is_default=False)
        )
        await self.session.execute(stmt)

    async def district_points(self) -> list[GeoPoint]:
        """District centroids, for resolving which district a pin falls in."""
        stmt = select(District.id, District.centroid_lat, District.centroid_lng).where(
            District.centroid_lat.is_not(None), District.centroid_lng.is_not(None)
        )
        result = await self.session.execute(stmt)
        return [
            GeoPoint(id=row[0], lat=float(row[1]), lng=float(row[2]))
            for row in result.all()
            if row[1] is not None and row[2] is not None
        ]
