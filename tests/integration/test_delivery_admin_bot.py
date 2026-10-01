from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import cmd_delivery_rules, handle_delivery_rule_update
from app.core.config import settings
from app.db.models.shop import District, Shop, ShopDeliveryRule
from app.db.models.user import User


@pytest.mark.asyncio
async def test_bot_admin_shows_and_saves_fixed_tashkent_city_delivery(
    test_session: AsyncSession,
) -> None:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    test_session.add(district)
    await test_session.flush()
    shop = Shop(
        name=settings.house_shop_name,
        phone=settings.house_shop_phone,
        district_id=district.id,
        address="Tashkent",
    )
    admin = User(tg_id=710001, full_name="Admin", role="admin")
    test_session.add_all([shop, admin])
    await test_session.flush()
    test_session.add(
        ShopDeliveryRule(
            shop_id=shop.id,
            district_id=district.id,
            fee=Decimal("0"),
            free_above=Decimal("1000"),
            min_order=Decimal("100000"),
            eta_hours=24,
        )
    )
    await test_session.commit()

    message = SimpleNamespace(text="/delivery_rules", answer=AsyncMock())
    state = SimpleNamespace(set_state=AsyncMock(), clear=AsyncMock())
    await cmd_delivery_rules(message, admin, test_session, state, lang="uz_latn")

    displayed = message.answer.await_args.args[0]
    assert "50 000 so'm" in displayed
    assert "100 000" not in displayed
    assert "(24h)" not in displayed

    message.answer.reset_mock()
    message.text = "dostavka Chilonzor 0 free:1 min:100000"
    await handle_delivery_rule_update(message, admin, test_session, state, lang="uz_latn")
    assert "yangilandi" in message.answer.await_args.args[0]

    saved = await test_session.scalar(
        select(ShopDeliveryRule).where(
            ShopDeliveryRule.shop_id == shop.id,
            ShopDeliveryRule.district_id == district.id,
        )
    )
    assert saved is not None
    assert saved.fee == Decimal("50000")
    assert saved.free_above is None
    assert saved.min_order == Decimal("0")
