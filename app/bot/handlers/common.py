from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.inline import get_district_keyboard, get_language_keyboard
from app.bot.keyboards.reply import get_main_menu_keyboard, get_phone_request_keyboard
from app.bot.states import RegistrationStates
from app.core.i18n import t
from app.db.models.user import User
from app.db.repositories.shop_repo import ShopRepository

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    lang: str,
) -> None:
    """Handle /start: if user has no language/district, start onboarding flow."""
    await state.clear()

    if not user.lang or user.district_id is None:
        await state.set_state(RegistrationStates.waiting_for_language)
        await message.answer(
            t("choose_language", lang="uz_latn"),
            reply_markup=get_language_keyboard(),
        )
    else:
        is_shop_owner = user.role in ("shop_owner", "admin")
        await message.answer(
            t("welcome_done", lang=lang),
            reply_markup=get_main_menu_keyboard(lang=lang, is_shop_owner=is_shop_owner),
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

    shop_repo = ShopRepository(session)
    districts = await shop_repo.list_districts()

    await state.set_state(RegistrationStates.waiting_for_district)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            t("choose_district", lang=new_lang),
            reply_markup=get_district_keyboard(districts, lang=new_lang),
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

    await state.set_state(RegistrationStates.waiting_for_phone)
    if isinstance(callback.message, Message):
        await callback.message.delete()
        await callback.message.answer(
            t("request_phone", lang=lang),
            reply_markup=get_phone_request_keyboard(lang=lang),
        )


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
    await message.answer(
        t("welcome_done", lang=lang),
        reply_markup=get_main_menu_keyboard(lang=lang, is_shop_owner=is_shop_owner),
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
    await message.answer(
        t("welcome_done", lang=lang),
        reply_markup=get_main_menu_keyboard(lang=lang, is_shop_owner=is_shop_owner),
    )


@router.message(Command("cancel"))
@router.message(F.text.in_(["❌ Bekor qilish", "❌ Бекор қилиш", "❌ Отмена"]))
async def cmd_cancel(message: Message, state: FSMContext, user: User, lang: str) -> None:
    await state.clear()
    is_shop_owner = user.role in ("shop_owner", "admin")
    await message.answer(
        t("action_cancelled", lang=lang),
        reply_markup=get_main_menu_keyboard(lang=lang, is_shop_owner=is_shop_owner),
    )


@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Созламалар", "⚙️ Настройки"]))
async def menu_settings(message: Message, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.waiting_for_language)
    await message.answer(
        t("choose_language", lang="uz_latn"),
        reply_markup=get_language_keyboard(),
    )
