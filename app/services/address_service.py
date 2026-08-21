"""Turning a dropped pin into something we can deliver to.

Three things have to happen and only one of them is a question for the
customer: reverse-geocode the pin into words, resolve which district it falls
in (delivery rules are per district), and have the customer confirm the words.
The district is never asked -- it is derivable, and every question removed from
signup is a customer who finishes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User, UserAddress
from app.db.repositories.address_repo import AddressRepository
from app.domain.geo import nearest_point
from app.services.geocoding_service import GeocodingService


@dataclass(frozen=True)
class ResolvedLocation:
    lat: Decimal
    lng: Decimal
    address_text: str | None
    district_id: int | None

    @property
    def needs_manual_address(self) -> bool:
        """True when the geocoder gave us nothing to show for confirmation."""
        return not self.address_text

    @property
    def outside_service_area(self) -> bool:
        return self.district_id is None


class AddressService:
    def __init__(
        self,
        session: AsyncSession,
        geocoder: GeocodingService | None = None,
    ) -> None:
        self.session = session
        self.repo = AddressRepository(session)
        self.geocoder = geocoder or GeocodingService()

    async def resolve(self, lat: float, lng: float, lang: str) -> ResolvedLocation:
        """Geocode the pin and work out its district. Never raises."""
        address_text = await self.geocoder.reverse_geocode(lat, lng, lang=lang)
        district_id = nearest_point(
            lat,
            lng,
            await self.repo.district_points(),
            max_km=settings.district_match_max_km,
        )
        return ResolvedLocation(
            lat=Decimal(str(lat)),
            lng=Decimal(str(lng)),
            address_text=address_text,
            district_id=district_id,
        )

    async def save(
        self,
        user: User,
        resolved: ResolvedLocation,
        address_text: str,
        *,
        label: str | None = None,
        make_default: bool = False,
    ) -> UserAddress:
        """Persist a confirmed address and keep the user's district in step.

        The user's own district is updated from their default address so quoting
        still has somewhere to price delivery from before an address is picked
        at checkout.
        """
        address = await self.repo.add(
            user_id=user.id,
            lat=resolved.lat,
            lng=resolved.lng,
            address_text=address_text.strip(),
            district_id=resolved.district_id,
            label=label,
            make_default=make_default,
        )
        if address.is_default and resolved.district_id is not None:
            user.district_id = resolved.district_id
        await self.session.flush()
        return address

    async def list_for(self, user: User) -> list[UserAddress]:
        return list(await self.repo.list_for_user(user.id))

    async def default_for(self, user: User) -> UserAddress | None:
        return await self.repo.get_default(user.id)
