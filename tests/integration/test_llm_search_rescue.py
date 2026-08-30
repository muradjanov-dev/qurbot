"""The catalog search gets a second chance, in the model's words.

The worst answer this bot can give is "katalogda topilmadi" for a product it
sells. It happened whenever the customer's wording shared no trigrams with the
catalog entry: with no candidates, there was nothing for the model to choose
between, so it was never asked, and the line died there.

Now the empty-handed line goes to the model too. It cannot pick an id out of an
empty list, but it can say what the customer means in catalog wording, and the
search runs again on that -- deterministically, with no second model call. When
that lands, the customer's own phrasing is written back as an alias, so the
next person to say it that way is answered by the exact-match stage for free.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.catalog import ProductAlias
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.llm.models import BatchDisambiguationResult, BatchLineDecision, BatchLineInput
from app.services.catalog_service import CatalogService
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def _full_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enabled_category_slugs", [])


class _NamingClient:
    """A model that never picks an id and always names the product instead.

    Exactly the shape of answer the empty-candidate case can produce, and the
    only part of the model's behaviour this test is about.
    """

    def __init__(self, term: str) -> None:
        self.term = term
        self.batches: list[list[BatchLineInput]] = []

    async def disambiguate_batch(
        self, lines: list[BatchLineInput], lang: str = "uz_latn"
    ) -> BatchDisambiguationResult:
        self.batches.append(lines)
        return BatchDisambiguationResult(
            lines={
                line.line_no: BatchLineDecision(
                    line_no=line.line_no,
                    canonical_id=None,
                    confidence=0.0,
                    reason="no candidates in the list",
                    question="Qalinligi qancha?",
                    search_term=self.term,
                )
                for line in lines
            }
        )

    async def parse_whole_message(self, message_text: str) -> object:
        raise AssertionError("the deterministic parser handles this basket")


@pytest.mark.asyncio
async def test_a_line_the_search_missed_is_rescued_by_the_model(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session)

    client = _NamingClient(term="fanera 12mm")
    service = CatalogService(
        CatalogRepository(test_session),
        OpsRepository(test_session),
        llm_client=client,  # type: ignore[arg-type]
    )

    # Nothing in the catalog shares trigrams with this, so Stage 2 comes back
    # empty -- the case that used to end at "katalogda topilmadi".
    results = await service.parse_and_match_basket("10 dona qalinroq yog'och list")
    assert len(results) == 1
    _line, decision = results[0]

    assert client.batches, "an empty-handed line must still reach the model"
    assert decision.canonical_id is not None, "the retried search should have landed"
    assert decision.method == "llm_search"
    assert decision.clarify_question == "Qalinligi qancha?"


@pytest.mark.asyncio
async def test_the_rescue_teaches_the_catalog_the_customer_s_wording(
    test_session: AsyncSession,
) -> None:
    await seed_database(test_session)

    service = CatalogService(
        CatalogRepository(test_session),
        OpsRepository(test_session),
        llm_client=_NamingClient(term="fanera 12mm"),  # type: ignore[arg-type]
    )
    await service.parse_and_match_basket("10 dona qalinroq yog'och list")

    aliases = await test_session.execute(select(ProductAlias).where(ProductAlias.source == "llm"))
    written = aliases.scalars().all()
    assert written, "the phrasing that needed rescuing should be learned"
    assert all(a.is_approved is False for a in written), "learned aliases await review"


@pytest.mark.asyncio
async def test_a_term_that_finds_nothing_leaves_the_line_as_it_was(
    test_session: AsyncSession,
) -> None:
    """A wrong suggestion must not invent a match."""
    await seed_database(test_session)

    service = CatalogService(
        CatalogRepository(test_session),
        OpsRepository(test_session),
        llm_client=_NamingClient(term="qwertyuiop asdfghjkl"),  # type: ignore[arg-type]
    )
    results = await service.parse_and_match_basket("10 dona qalinroq yog'och list")
    _line, decision = results[0]

    assert decision.canonical_id is None
    assert decision.status == "unresolved"
