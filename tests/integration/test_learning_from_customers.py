"""The bot gets better with use, not only with redeploys.

A customer picking a product from the "which did you mean" list is the
strongest signal the system ever receives: not a model's guess but a person
confirming what they meant. Remembering it turns the next occurrence of that
phrasing into an exact match -- answered by Stage 1 for nothing, with no
scoring and no model call.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import CanonicalProduct, Category, ProductAlias
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.domain.normalize.text import normalize_query
from app.domain.parsing.models import ParsedLine
from app.llm.client import LLMClient
from app.services.catalog_service import CatalogService

CUSTOMER_WORDING = "qalinroq yogoch list"


@pytest.fixture(autouse=True)
def _full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enabled_category_slugs", [])


async def _product(session: AsyncSession) -> CanonicalProduct:
    category = Category(slug="plita-va-fanera", name_uz="Plita", name_ru="Плита")
    session.add(category)
    await session.flush()
    product = CanonicalProduct(
        slug="fanera-12mm",
        name_uz="Fanera 12 mm 1525x1525",
        name_uz_cyrl="Фанера 12 мм",
        name_ru="Фанера 12 мм",
        category_id=category.id,
        base_unit_code="dona",
        search_doc="fanera 12 mm 1525x1525",
    )
    session.add(product)
    await session.flush()
    return product


@pytest.mark.asyncio
async def test_a_confirmed_pick_is_remembered(test_session: AsyncSession) -> None:
    product = await _product(test_session)
    repo = CatalogRepository(test_session)

    learned = await repo.learn_alias_from_customer(
        canonical_id=product.id,
        alias_norm=normalize_query(CUSTOMER_WORDING).text_norm,
        alias_raw=CUSTOMER_WORDING,
    )

    assert learned is not None
    assert learned.is_approved is True, "a person confirmed it; it takes effect now"
    assert learned.source == "user"


@pytest.mark.asyncio
async def test_the_next_customer_is_answered_for_nothing(test_session: AsyncSession) -> None:
    """Stage 1 is an exact hit: no scoring, no model, no cost."""
    product = await _product(test_session)
    repo = CatalogRepository(test_session)
    await repo.learn_alias_from_customer(
        canonical_id=product.id,
        alias_norm=normalize_query(CUSTOMER_WORDING).text_norm,
        alias_raw=CUSTOMER_WORDING,
    )

    service = CatalogService(repo, OpsRepository(test_session), llm_client=LLMClient())
    line = ParsedLine(
        line_no=1,
        raw_text=f"10 dona {CUSTOMER_WORDING}",
        parsed_name=CUSTOMER_WORDING,
        qty=Decimal("10"),
        unit_code="dona",
    )
    _parsed, decision = await service.match_parsed_line(line)

    assert decision.method == "alias"
    assert decision.canonical_id == product.id
    assert decision.status == "auto_accept"


@pytest.mark.asyncio
async def test_a_curated_mapping_is_never_repointed(test_session: AsyncSession) -> None:
    """One tap must not overwrite an alias someone deliberately set."""
    product = await _product(test_session)
    other = CanonicalProduct(
        slug="osb-9mm",
        name_uz="OSB-3 9 mm",
        name_uz_cyrl="ОСБ-3 9 мм",
        name_ru="ОСБ-3 9 мм",
        category_id=product.category_id,
        base_unit_code="dona",
        search_doc="osb-3 9 mm",
    )
    test_session.add(other)
    await test_session.flush()

    repo = CatalogRepository(test_session)
    norm = normalize_query(CUSTOMER_WORDING).text_norm
    await repo.create_approved_alias(
        canonical_id=product.id, alias_norm=norm, alias_raw=CUSTOMER_WORDING, source="admin"
    )

    again = await repo.learn_alias_from_customer(
        canonical_id=other.id, alias_norm=norm, alias_raw=CUSTOMER_WORDING
    )

    assert again is None
    kept = await repo.get_approved_alias(norm)
    assert kept is not None and kept.canonical_id == product.id


@pytest.mark.asyncio
async def test_nothing_is_learned_from_noise(test_session: AsyncSession) -> None:
    """ "5", "??" and the like identify no product and must not become aliases."""
    product = await _product(test_session)
    repo = CatalogRepository(test_session)

    for junk in ("5", "??", "  ", "12"):
        assert (
            await repo.learn_alias_from_customer(
                canonical_id=product.id, alias_norm=junk, alias_raw=junk
            )
            is None
        )

    rows = (await test_session.execute(select(ProductAlias))).scalars().all()
    assert rows == []
