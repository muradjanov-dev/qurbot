from app.bot.keyboards.inline import (
    get_basket_actions_keyboard,
    get_candidate_picker_keyboard,
    get_district_keyboard,
    get_language_keyboard,
    get_quote_carousel_keyboard,
    get_reregister_confirm_keyboard,
    get_settings_inline_keyboard,
    get_shop_order_decision_keyboard,
)
from app.bot.keyboards.reply import (
    get_cabinet_keyboard,
    get_cancel_keyboard,
    get_main_menu_keyboard,
    get_phone_request_keyboard,
)
from app.db.models.shop import District
from app.domain.matching.models import CandidateMatch


def test_language_keyboard() -> None:
    kb = get_language_keyboard()
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "set_lang:uz_latn"
    assert kb.inline_keyboard[1][0].callback_data == "set_lang:uz_cyrl"
    assert kb.inline_keyboard[2][0].callback_data == "set_lang:ru"

    kb_back = get_language_keyboard(change_only=True, show_back=True, lang="uz_latn")
    assert len(kb_back.inline_keyboard) == 4
    assert kb_back.inline_keyboard[0][0].callback_data == "chg_lang:uz_latn"
    assert kb_back.inline_keyboard[3][0].callback_data == "settings:back"


def test_settings_keyboards() -> None:
    kb = get_settings_inline_keyboard(lang="uz_latn")
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "settings:language"
    assert kb.inline_keyboard[1][0].callback_data == "settings:reregister"

    confirm_kb = get_reregister_confirm_keyboard(lang="uz_latn")
    assert len(confirm_kb.inline_keyboard) == 1
    assert len(confirm_kb.inline_keyboard[0]) == 2
    assert confirm_kb.inline_keyboard[0][0].callback_data == "reregister:confirm"
    assert confirm_kb.inline_keyboard[0][1].callback_data == "reregister:cancel"


def test_district_keyboard() -> None:
    districts = [
        District(id=1, name_uz="Chilonzor", name_ru="Чиланзар"),
        District(id=2, name_uz="Yunusobod", name_ru="Юнусабад"),
        District(id=3, name_uz="Mirzo Ulug'bek", name_ru="Мирзо-Улугбек"),
    ]
    kb = get_district_keyboard(districts, lang="uz_latn")
    # 2 columns layout
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].text == "Chilonzor"
    assert kb.inline_keyboard[0][1].text == "Yunusobod"
    assert kb.inline_keyboard[1][0].text == "Mirzo Ulug'bek"


def test_basket_actions_keyboard() -> None:
    """Fix the list first, order it last -- the order button closes the screen."""
    kb = get_basket_actions_keyboard(lang="uz_latn")
    assert len(kb.inline_keyboard) == 3

    # "Rewrite the whole list" is gone: each line now has its own change and
    # remove buttons, which is what that button was a blunt substitute for.
    editing = [b.callback_data for b in kb.inline_keyboard[0]]
    assert editing == ["add_item", "clear_basket"]
    assert kb.inline_keyboard[1][0].callback_data == "back_to_menu"

    order_button = kb.inline_keyboard[2][0]
    assert order_button.callback_data == "calculate_quotes"
    assert order_button.text.startswith("✅")


def test_candidate_picker_keyboard() -> None:
    cands = [
        CandidateMatch(
            canonical_id=10,
            slug="cement-m400",
            name_uz="Qizilqum Sement M400",
            score=0.75,
        ),
        CandidateMatch(
            canonical_id=11,
            slug="bekobod-m400",
            name_uz="Bekobod Sement M400",
            score=0.68,
        ),
    ]
    kb = get_candidate_picker_keyboard(line_no=1, candidates=cands, lang="uz_latn")
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "pick_cand:1:10"
    assert kb.inline_keyboard[1][0].callback_data == "pick_cand:1:11"
    assert kb.inline_keyboard[2][0].callback_data == "pick_custom:1"


def test_quote_carousel_keyboard() -> None:
    kb = get_quote_carousel_keyboard(current_index=0, total_variants=4, lang="uz_latn")
    # Row 1: ◀️, 1/4, ▶️
    # Row 2: Select
    # Row 3: PDF, Back to basket
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "nav_quote:3"  # Wraps to last
    assert kb.inline_keyboard[0][1].text == "1/4"
    assert kb.inline_keyboard[0][2].callback_data == "nav_quote:1"
    assert kb.inline_keyboard[1][0].callback_data == "select_quote:0"


def test_quote_carousel_offers_a_way_back_to_the_basket() -> None:
    """Recalculating re-ran the same optimisation over the same basket.

    A customer who spotted a wrong line on the quote screen had no way back to
    fix it, so the button that returned the same numbers is now the way out.
    """
    kb = get_quote_carousel_keyboard(current_index=0, total_variants=4, lang="uz_latn")
    callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]
    assert "back_to_basket" in callbacks
    assert "calculate_quotes" not in callbacks


def test_quote_carousel_hides_ordering_when_nothing_was_sourced() -> None:
    """A variant covering 0 products must not offer a confirm button.

    An enabled button is a promise that pressing it does something; ordering a
    0-item, 0 so'm quote is not something any shop can fulfil.
    """
    kb = get_quote_carousel_keyboard(
        current_index=0, total_variants=1, lang="uz_latn", is_orderable=False
    )
    callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]
    assert not any(cb and cb.startswith("select_quote:") for cb in callbacks)
    assert not any(cb and cb.startswith("pdf_quote:") for cb in callbacks)
    assert "back_to_basket" in callbacks


def test_shop_order_decision_keyboard() -> None:
    kb = get_shop_order_decision_keyboard(order_part_id=42)
    assert len(kb.inline_keyboard) == 1
    assert kb.inline_keyboard[0][0].callback_data == "shop_order:accept:42"
    assert kb.inline_keyboard[0][1].callback_data == "shop_order:reject:42"


def test_main_menu_keyboard() -> None:
    kb_cust = get_main_menu_keyboard(lang="uz_latn", is_shop_owner=False)
    assert len(kb_cust.keyboard) == 2

    kb_shop = get_main_menu_keyboard(lang="uz_latn", is_shop_owner=True)
    assert len(kb_shop.keyboard) == 3


def test_phone_request_keyboard() -> None:
    kb = get_phone_request_keyboard(lang="uz_latn")
    assert kb.keyboard[0][0].request_contact is True
    assert kb.keyboard[1][0].text == "⏭ O'tkazib yuborish"


def test_cancel_keyboard() -> None:
    kb = get_cancel_keyboard(lang="uz_latn")
    assert kb.keyboard[0][0].text == "❌ Bekor qilish"


def test_cabinet_keyboard() -> None:
    kb = get_cabinet_keyboard(lang="uz_latn")
    assert len(kb.keyboard) == 3
    assert kb.keyboard[0][0].text == "📦 Buyurtmalarim"
    assert kb.keyboard[0][1].text == "📍 Manzillarim"
    assert kb.keyboard[1][0].text == "⚙️ Sozlamalar"
    assert kb.keyboard[1][1].text == "🔄 0 dan qayta ro'yxatdan o'tish"
    assert kb.keyboard[2][0].text == "⬅️ Asosiy menyu"
