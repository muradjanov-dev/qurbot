"""A staged price list is read back to its owner a page at a time.

Confirming an import used to mean agreeing with a count. These tests hold the
replacement in place: the rows themselves, twenty to a screen, with navigation
that stays inside the file and a confirm button that still ends at the same
apply step.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import _render_import_page
from app.core.config import settings
from app.db.models.catalog import Category
from app.db.models.shop import District, Shop
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository

ROW_COUNT = 25


async def _staged_batch(session: AsyncSession) -> int:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()
    shop = Shop(
        name="Ark buloq",
        phone="+998901112233",
        district_id=district.id,
        address="Chilonzor 9",
        is_active=True,
    )
    category = Category(slug="plita-va-fanera", name_uz="Plita va fanera", name_ru="Плита")
    session.add_all([shop, category])
    await session.flush()

    canonical = await CatalogRepository(session).create_canonical_product(
        slug="fanera-12mm",
        name_uz="Fanera 12 mm 1525x1525",
        name_uz_cyrl="Фанера 12 мм",
        name_ru="Фанера 12 мм",
        category_id=category.id,
        base_unit_code="dona",
    )

    shop_repo = ShopRepository(session)
    batch = await shop_repo.create_import_batch(
        shop_id=shop.id, filename="narxlar.xlsx", total_rows=ROW_COUNT
    )
    await shop_repo.create_import_rows(
        batch.id,
        [
            {
                "row_no": n,
                "raw_payload": {
                    "raw_name": f"fanera 12 qator {n}",
                    "raw_unit": "dona",
                    "raw_price": "278000",
                    "raw_qty": "40",
                },
                "matched_canonical_id": canonical.id if n % 2 else None,
                "resolution": "auto" if n % 2 else "manual",
            }
            for n in range(1, ROW_COUNT + 1)
        ],
    )
    await session.flush()
    return batch.id


@pytest.mark.asyncio
async def test_the_first_page_shows_the_rows_not_a_count(test_session: AsyncSession) -> None:
    batch_id = await _staged_batch(test_session)

    text, keyboard = await _render_import_page(test_session, batch_id, 1, "uz_latn")

    assert "Fanera 12 mm 1525x1525" in text, "a matched row shows the catalogue name"
    assert "278 000" in text, "the price is what the owner was asked to check"
    assert "1/2" in str(keyboard), "navigation says where in the file this is"
    assert f"{ROW_COUNT}" in text


@pytest.mark.asyncio
async def test_the_second_page_holds_the_remainder(test_session: AsyncSession) -> None:
    batch_id = await _staged_batch(test_session)
    page_size = settings.import_preview_page_size

    text, _ = await _render_import_page(test_session, batch_id, 2, "uz_latn")

    body = text.split("\n\n", 1)[1]
    first_line = body.splitlines()[0]
    assert first_line.startswith(f"{page_size + 1}."), "page 2 starts where page 1 stopped"
    assert f"{ROW_COUNT}." in body, "and runs to the last row"
    # A row needing review carries a second, indented line, so count the rows
    # themselves rather than the lines they occupy.
    numbered = [line for line in body.splitlines() if line[:1].isdigit()]
    assert len(numbered) == ROW_COUNT - page_size


@pytest.mark.asyncio
async def test_a_page_past_the_end_lands_on_the_last_one(test_session: AsyncSession) -> None:
    """Navigation wraps, so a page number out of range must not blank the screen."""
    batch_id = await _staged_batch(test_session)

    text, keyboard = await _render_import_page(test_session, batch_id, 99, "uz_latn")

    assert "2/2" in str(keyboard)
    assert text.strip()


@pytest.mark.asyncio
async def test_confirm_and_cancel_survive_the_paging(test_session: AsyncSession) -> None:
    """Paging is a view; the decision buttons stay on every page."""
    batch_id = await _staged_batch(test_session)

    for page in (1, 2):
        _text, keyboard = await _render_import_page(test_session, batch_id, page, "uz_latn")
        callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
        assert f"import_confirm:{batch_id}" in callbacks
        assert f"import_cancel:{batch_id}" in callbacks
