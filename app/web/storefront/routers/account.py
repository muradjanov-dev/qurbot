"""The customer's cabinet: pebbles, saved delivery places, language."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.db.repositories.address_repo import AddressRepository
from app.db.repositories.ops_repo import OpsRepository
from app.db.session import get_db_session
from app.services.address_service import AddressService
from app.web.storefront.deps import current_lang, current_user, render

router = APIRouter(tags=["storefront"])

_ACCOUNT_URL = "/account"


@router.get("/account")
async def account_page(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    if user is None:
        return RedirectResponse("/login?next=/account", status_code=303)

    pebbles = await OpsRepository(session).get_pebble_balance(user.id)
    addresses = await AddressService(session).list_for(user)
    return render(
        request,
        "account.html",
        user=user,
        lang=lang,
        pebbles=pebbles,
        addresses=addresses,
        bot_username=settings.telegram_login_bot_username,
    )


@router.post("/account/addresses")
async def add_address(
    request: Request,
    address_text: str = Form(...),
    lat: str = Form(...),
    lng: str = Form(...),
    label: str = Form(default=""),
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    """Save a delivery place from a confirmed pin.

    Anchored on coordinates, not text, for the same reason the bot is: a typed
    Tashkent street address often does not resolve to a findable place, and the
    pin is what the courier actually uses.
    """
    if user is None:
        return RedirectResponse("/login?next=/account", status_code=303)

    text = address_text.strip()
    if not text:
        return RedirectResponse(f"{_ACCOUNT_URL}?msg=web_error_generic", status_code=303)

    try:
        latitude, longitude = Decimal(lat), Decimal(lng)
    except (ArithmeticError, ValueError):
        return RedirectResponse(f"{_ACCOUNT_URL}?msg=web_error_generic", status_code=303)

    repo = AddressRepository(session)
    resolved = await AddressService(session).resolve(float(latitude), float(longitude), lang=lang)
    address = await repo.add(
        user_id=user.id,
        lat=latitude,
        lng=longitude,
        address_text=text,
        district_id=resolved.district_id,
        label=label.strip() or None,
        make_default=not await repo.get_default(user.id),
    )
    # Delivery is priced per district, so the account's district follows its
    # default address -- otherwise a quote has nowhere to deliver from.
    if address.is_default and address.district_id is not None:
        user.district_id = address.district_id
    await session.flush()
    return RedirectResponse(f"{_ACCOUNT_URL}?msg=web_saved", status_code=303)


@router.post("/account/addresses/{address_id}/default")
async def make_default(
    address_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    if user is None:
        return RedirectResponse("/login?next=/account", status_code=303)

    address = await AddressRepository(session).set_default(user.id, address_id)
    if address is not None and address.district_id is not None:
        user.district_id = address.district_id
        await session.flush()
    return RedirectResponse(f"{_ACCOUNT_URL}?msg=web_saved", status_code=303)


@router.post("/account/addresses/{address_id}/delete")
async def delete_address(
    address_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> Response:
    if user is None:
        return RedirectResponse("/login?next=/account", status_code=303)

    await AddressRepository(session).delete(user.id, address_id)
    return RedirectResponse(f"{_ACCOUNT_URL}?msg=web_saved", status_code=303)
