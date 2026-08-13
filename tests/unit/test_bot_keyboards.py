from app.bot.keyboards.inline import (
    get_basket_actions_keyboard,
    get_candidate_picker_keyboard,
    get_district_keyboard,
    get_language_keyboard,
    get_quote_carousel_keyboard,
    get_shop_order_decision_keyboard,
)
from app.bot.keyboards.reply import (
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
    kb = get_basket_actions_keyboard(lang="uz_latn")
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "calculate_quotes"
    assert kb.inline_keyboard[2][0].callback_data == "back_to_menu"


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
    # Row 3: PDF, Recalculate
    assert len(kb.inline_keyboard) == 3
    assert kb.inline_keyboard[0][0].callback_data == "nav_quote:3"  # Wraps to last
    assert kb.inline_keyboard[0][1].text == "1/4"
    assert kb.inline_keyboard[0][2].callback_data == "nav_quote:1"
    assert kb.inline_keyboard[1][0].callback_data == "select_quote:0"


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
