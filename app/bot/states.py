from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Signup: language, then a location pin. That is the whole thing.

    District is derived from the pin instead of being asked, and the phone is
    collected at checkout where it is actually needed -- every question moved
    out of signup is a customer who finishes it.
    """

    waiting_for_language = State()
    waiting_for_location = State()
    confirming_address = State()
    editing_address_text = State()
    # Kept for the customer who declines to share a location: they pick a
    # district by hand instead, so refusing the pin is not a dead end.
    waiting_for_district = State()
    waiting_for_phone = State()


class BasketStates(StatesGroup):
    waiting_for_basket_text = State()
    editing_line = State()
    adding_item = State()
    entering_qty_for_product = State()
    viewing_quotes = State()


class OrderCheckoutStates(StatesGroup):
    confirming_phone = State()
    choosing_address = State()
    awaiting_new_location = State()
    confirming_new_address = State()
    entering_address = State()
    entering_comment = State()
    confirming_order = State()


class ShopListingStates(StatesGroup):
    """Product upload.

    The normal path is a single message -- photos plus a caption -- and none of
    these states are entered at all. They exist only for the pieces the caption
    did not supply, so the bot asks about exactly what is missing and nothing
    else. The answers themselves live in shop_product_drafts, so losing the
    state loses at most one question, never the listing.
    """

    quick_entry = State()
    entering_name = State()
    choosing_pack = State()
    entering_pack_size = State()
    entering_price = State()
    confirming_price = State()
    editing_saved = State()


class AdminPanelStates(StatesGroup):
    """Admin panel actions that need a follow-up answer."""

    entering_admin_id = State()


class AdminShopStates(StatesGroup):
    """Admin-only wizard for onboarding a shop and its owners."""

    entering_name = State()
    entering_phone = State()
    choosing_district = State()
    entering_address = State()
    entering_owner_id = State()


class ShopOwnerStates(StatesGroup):
    waiting_for_quick_price = State()
    waiting_for_excel_upload = State()
    editing_product_price = State()
    reviewing_import_batch = State()
    editing_delivery_rule = State()
    editing_product_price_value = State()
