from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.common import esc
from app.bot.keyboards.inline import (
    get_address_confirm_keyboard,
    get_district_keyboard,
    get_language_keyboard,
)
from app.bot.keyboards.reply import (
    get_cabinet_keyboard,
    get_location_request_keyboard,
    get_main_menu_keyboard,
)
from app.bot.states import RegistrationStates
from app.core.config import settings
from app.core.i18n import t
from app.db.models.user import User
from app.db.repositories.ops_repo import OpsRepository
from app.db.repositories.shop_repo import ShopRepository
from app.services.address_service import AddressService, ResolvedLocation

router = Router(name="common")


@router.message(CommandStart())
@router.message(Command("menu"))
@router.message(F.text.in_(["📋 Ro'yxat yuborish", "📋 Рўйхат юбориш", "📋 Отправить список"]))
@router.message(F.text.in_(["🏠 Asosiy menyu", "🏠 Асосий меню", "🏠 Главное меню"]))
async def cmd_start(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Handle /start: always offer the language picker first.

    Returning users are not walked through the rest of onboarding again --
    callback_set_lang sends them straight to the menu once district is known.
    """
    await state.clear()
    await state.set_state(RegistrationStates.waiting_for_language)
    await message.answer(
        t("choose_language", lang=lang or "uz_latn"),
        reply_markup=get_language_keyboard(),
    )


@router.callback_query(F.data.startswith("set_lang:"), RegistrationStates.waiting_for_language)
async def callback_set_lang(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
) -> None:
    if not callback.data:
        return
    new_lang = callback.data.split(":")[1]
    user.lang = new_lang
    await session.flush()

    if not isinstance(callback.message, Message):
        return

    if user.district_id is not None:
        # Already onboarded -- /start just changed the language, so go straight
        # to the menu instead of re-asking district and phone.
        await state.clear()
        is_shop_owner = user.role in ("shop_owner", "admin")
        is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
        await callback.message.edit_text(t("language_changed", lang=new_lang))
        await callback.message.answer(
            t("welcome_done", lang=new_lang),
            reply_markup=get_main_menu_keyboard(
                lang=new_lang, is_shop_owner=is_shop_owner, is_admin=is_admin
            ),
        )
        await callback.answer()
        return

    # Ask for a pin, not a district. The district is derivable from it, and a
    # dropped pin is also what the courier actually needs -- a typed Tashkent
    # street address frequently does not resolve to a findable place.
    await state.set_state(RegistrationStates.waiting_for_location)
    await callback.message.delete()
    await callback.message.answer(
        t("request_location", lang=new_lang),
        reply_markup=get_location_request_keyboard(lang=new_lang),
    )
    await callback.answer()


@router.message(F.location, RegistrationStates.waiting_for_location)
async def msg_registration_location(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if message.location is None:
        return
    await _handle_location(
        message,
        state,
        user,
        session,
        lang,
        lat=message.location.latitude,
        lng=message.location.longitude,
        next_state=RegistrationStates.confirming_address,
        text_state=RegistrationStates.editing_address_text,
    )


@router.message(
    F.text.in_(
        [
            "\U0001f5fa Tumanni qo'lda tanlash",
            "\U0001f5fa Туманни қўлда танлаш",
            "\U0001f5fa Выбрать район вручную",
        ]
    ),
    RegistrationStates.waiting_for_location,
)
async def msg_registration_district_fallback(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    lang: str,
) -> None:
    """Declining to share a location must not be a dead end."""
    shop_repo = ShopRepository(session)
    districts = await shop_repo.list_districts()
    await state.set_state(RegistrationStates.waiting_for_district)
    await message.answer(
        t("choose_district", lang=lang),
        reply_markup=get_district_keyboard(districts, lang=lang),
    )


async def _handle_location(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
    *,
    lat: float,
    lng: float,
    next_state: State,
    text_state: State,
) -> None:
    """Geocode a pin and ask the customer to confirm what came back.

    Shared by signup and checkout: both need the same confirm-or-correct step,
    because a geocoder's guess is a suggestion and the customer is the
    authority on where they live.
    """
    service = AddressService(session)
    resolved = await service.resolve(lat, lng, lang=lang)
    await state.update_data(
        pending_lat=str(resolved.lat),
        pending_lng=str(resolved.lng),
        pending_district_id=resolved.district_id,
    )

    if resolved.outside_service_area:
        await message.answer(t("address_outside_service_area", lang=lang))

    if resolved.needs_manual_address:
        await state.set_state(text_state)
        await message.answer(
            t("address_not_detected", lang=lang), reply_markup=ReplyKeyboardRemove()
        )
        return

    await state.update_data(pending_address=resolved.address_text)
    await state.set_state(next_state)
    await message.answer(
        t("address_detected", lang=lang, address=esc(resolved.address_text)),
        reply_markup=get_address_confirm_keyboard(lang=lang),
    )


@router.callback_query(F.data == "addr_edit", RegistrationStates.confirming_address)
async def callback_registration_address_edit(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(RegistrationStates.editing_address_text)
    await callback.message.answer(t("address_ask_text", lang=lang))
    await callback.answer()


@router.callback_query(F.data == "addr_ok", RegistrationStates.confirming_address)
async def callback_registration_address_ok(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    data = await state.get_data()
    await _save_registration_address(
        callback.message, state, user, session, lang, str(data.get("pending_address", ""))
    )
    await callback.answer()


@router.message(RegistrationStates.editing_address_text, F.text)
async def msg_registration_address_text(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not message.text or not message.text.strip():
        return
    await _save_registration_address(message, state, user, session, lang, message.text)


async def _save_registration_address(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
    address_text: str,
) -> None:
    data = await state.get_data()
    lat = data.get("pending_lat")
    lng = data.get("pending_lng")
    if lat is None or lng is None or not address_text.strip():
        return

    service = AddressService(session)
    resolved = ResolvedLocation(
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
        address_text=address_text,
        district_id=data.get("pending_district_id"),
    )
    await service.save(user, resolved, address_text, make_default=True)
    await session.flush()

    await state.clear()
    await message.answer(t("address_saved", lang=lang, address=esc(address_text.strip())))
    await _finish_registration(message, user, lang)


async def _finish_registration(message: Message, user: User, lang: str) -> None:
    """Signup ends here -- the phone is collected at checkout, where it is used."""
    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    await message.answer(
        t("welcome_done", lang=lang),
        reply_markup=get_main_menu_keyboard(
            lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
        ),
    )


@router.callback_query(F.data.startswith("set_district:"), RegistrationStates.waiting_for_district)
async def callback_set_district(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    if not callback.data:
        return
    dist_id = int(callback.data.split(":")[1])
    user.district_id = dist_id
    await session.flush()

    # Manual district is the fallback path, and it ends signup too: the phone
    # is asked at checkout, where it is actually needed.
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.delete()
        await _finish_registration(callback.message, user, lang)


@router.message(F.contact, RegistrationStates.waiting_for_phone)
async def msg_contact(
    message: Message,
    state: FSMContext,
    user: User,
    lang: str,
) -> None:
    if message.contact:
        await state.update_data(contact_phone=message.contact.phone_number)

    await state.clear()
    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    await message.answer(
        t("welcome_done", lang=lang),
        reply_markup=get_main_menu_keyboard(
            lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
        ),
    )


@router.message(F.text == "⏭ O'tkazib yuborish", RegistrationStates.waiting_for_phone)
@router.message(F.text == "⏭ Ўтказиб юбориш", RegistrationStates.waiting_for_phone)
@router.message(F.text == "⏭ Пропустить", RegistrationStates.waiting_for_phone)
async def msg_skip_phone(
    message: Message,
    state: FSMContext,
    user: User,
    lang: str,
) -> None:
    await state.clear()
    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    await message.answer(
        t("welcome_done", lang=lang),
        reply_markup=get_main_menu_keyboard(
            lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
        ),
    )


@router.message(Command("cancel"))
@router.message(F.text.in_(["❌ Bekor qilish", "❌ Бекор қилиш", "❌ Отмена"]))
async def cmd_cancel(message: Message, state: FSMContext, user: User, lang: str) -> None:
    await state.clear()
    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    await message.answer(
        t("action_cancelled", lang=lang),
        reply_markup=get_main_menu_keyboard(
            lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
        ),
    )


@router.message(F.text.in_(["👤 Kabinet", "👤 Кабинет"]))
async def menu_cabinet(message: Message, user: User, session: AsyncSession, lang: str) -> None:
    pebbles = await OpsRepository(session).get_pebble_balance(user.id)
    body = t("cabinet_title", lang=lang)
    balance = t("pebbles_balance", lang=lang, pebbles=pebbles)
    await message.answer(
        f"{body}\n\n{balance}",
        reply_markup=get_cabinet_keyboard(lang=lang),
    )


@router.message(F.text.in_(["⬅️ Asosiy menyu", "⬅️ Асосий меню", "⬅️ Главное меню"]))
async def menu_back_to_main(message: Message, user: User, state: FSMContext, lang: str) -> None:
    await state.clear()
    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    await message.answer(
        t("welcome_done", lang=lang),
        reply_markup=get_main_menu_keyboard(
            lang=lang, is_shop_owner=is_shop_owner, is_admin=is_admin
        ),
    )


@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Созламалар", "⚙️ Настройки"]))
async def menu_settings(message: Message, state: FSMContext, lang: str) -> None:
    # No registration state here: an already-onboarded user changing language
    # must not be walked back through district and phone.
    await state.clear()
    await message.answer(
        t("choose_language", lang=lang),
        reply_markup=get_language_keyboard(change_only=True),
    )


@router.callback_query(F.data.startswith("chg_lang:"))
async def callback_change_language(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
) -> None:
    if not callback.data:
        return
    new_lang = callback.data.split(":")[1]
    user.lang = new_lang
    await session.flush()

    is_shop_owner = user.role in ("shop_owner", "admin")
    is_admin = user.tg_id in settings.admin_tg_ids or user.role == "admin"
    if isinstance(callback.message, Message):
        await callback.message.edit_text(t("language_changed", lang=new_lang))
        await callback.message.answer(
            t("welcome_done", lang=new_lang),
            reply_markup=get_main_menu_keyboard(
                lang=new_lang, is_shop_owner=is_shop_owner, is_admin=is_admin
            ),
        )
    await callback.answer()


@router.message(F.text.in_(["📍 Manzillarim", "📍 Манзилларим", "📍 Мои адреса"]))
async def menu_my_addresses(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """List saved delivery places, and offer to add another.

    Kept read-mostly on purpose: the place a customer actually needs to choose
    an address is checkout, and that picker is where the choice belongs.
    """
    service = AddressService(session)
    addresses = await service.list_for(user)
    if not addresses:
        await state.set_state(RegistrationStates.waiting_for_location)
        await message.answer(t("addresses_empty", lang=lang))
        await message.answer(
            t("request_location", lang=lang),
            reply_markup=get_location_request_keyboard(lang=lang),
        )
        return

    lines = []
    for addr in addresses:
        mark = "📍" if addr.is_default else "•"
        label = f"<b>{esc(addr.label)}</b> — " if addr.label else ""
        lines.append(f"{mark} {label}{esc(addr.address_text)}")
    await message.answer("\n".join(lines))
