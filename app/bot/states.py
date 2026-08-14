from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_district = State()
    waiting_for_phone = State()


class BasketStates(StatesGroup):
    waiting_for_basket_text = State()
    editing_line = State()
    adding_item = State()
    viewing_quotes = State()


class OrderCheckoutStates(StatesGroup):
    confirming_phone = State()
    entering_address = State()
    entering_comment = State()
    confirming_order = State()


class ShopListingStates(StatesGroup):
    """Product upload wizard.

    These states only decide which question the bot is currently asking -- the
    answers themselves live in shop_product_drafts, so losing the state loses
    at most one question, never the listing.
    """

    choosing_category = State()
    entering_name = State()
    choosing_unit = State()
    entering_pack_size = State()
    entering_price = State()
    entering_qty = State()
    entering_description = State()
    uploading_photos = State()
    reviewing = State()


class ShopOwnerStates(StatesGroup):
    waiting_for_quick_price = State()
    waiting_for_excel_upload = State()
    editing_product_price = State()
    reviewing_import_batch = State()
    editing_delivery_rule = State()
