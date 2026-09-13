from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.services.catalog_service import CatalogService
from app.web.storefront.quoting import parse_basket_text


async def test_bot_and_web_share_matching_and_language(
    test_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "enabled_category_slugs", [])
    monkeypatch.setattr(settings, "llm_enabled", False)
    test_session.add(Unit(code="dona", name_uz="Dona", name_ru="Штука", dimension="count"))
    test_session.add(Category(id=1, slug="sheets", name_uz="Plitalar", name_ru="Плиты"))
    await test_session.flush()
    for thickness in (3, 12):
        name = f"Fanera {thickness}mm"
        test_session.add(
            CanonicalProduct(
                id=thickness,
                slug=f"fanera-{thickness}",
                name_uz=name,
                name_uz_cyrl=name,
                name_ru=name,
                category_id=1,
                base_unit_code="dona",
                search_doc=name.lower(),
                attributes={"thickness_mm": thickness},
                reference_price=Decimal(100),
            )
        )
    await test_session.flush()
    raw = "10 dona fanera"
    service = CatalogService(CatalogRepository(test_session), OpsRepository(test_session))
    bot = (await service.parse_and_match_basket(raw, lang="ru", require_offers=True))[0][1]
    web = (await parse_basket_text(test_session, raw, lang="ru"))[0]
    assert bot.status == "ask_user" and web["status"] == "choose"
    assert bot.clarify_question == web["clarify_question"] == "Выберите толщину или размер."
    assert {c.canonical_id for c in bot.candidates} == {
        c["canonical_id"] for c in web["candidates"]
    }
