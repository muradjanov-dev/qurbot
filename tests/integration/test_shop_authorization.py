"""Shop-scoped callbacks must reject ids belonging to somebody else's shop.

Callback data is chosen entirely by the client, so a shop owner can type
another shop's order or import id by hand. These cover the ownership checks
that stop that.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.shop import (
    _batch_belongs_to_user,
    _owns_shop,
    _row_belongs_to_user,
)
from app.db.models import District, ImportRow, User
from app.db.repositories import ShopRepository


async def _setup_two_shops(session: AsyncSession) -> tuple[User, User, int, int]:
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add(district)
    await session.flush()

    repo = ShopRepository(session)
    mine = await repo.create_shop("Meniki", "+998900000001", district.id, "A")
    theirs = await repo.create_shop("Begona", "+998900000002", district.id, "B")
    await repo.add_shop_owner(mine.id, tg_id=111)
    await repo.add_shop_owner(theirs.id, tg_id=222)

    me = User(tg_id=111, full_name="Me", lang="uz_latn", role="shop_owner")
    them = User(tg_id=222, full_name="Them", lang="uz_latn", role="shop_owner")
    session.add_all([me, them])
    await session.flush()
    return me, them, mine.id, theirs.id


@pytest.mark.asyncio
async def test_owns_shop_rejects_other_owners_shop(test_session: AsyncSession) -> None:
    me, them, mine_id, theirs_id = await _setup_two_shops(test_session)

    assert await _owns_shop(me, test_session, mine_id) is True
    assert await _owns_shop(me, test_session, theirs_id) is False
    assert await _owns_shop(them, test_session, theirs_id) is True
    assert await _owns_shop(them, test_session, mine_id) is False


@pytest.mark.asyncio
async def test_import_batch_and_row_ownership(test_session: AsyncSession) -> None:
    me, them, mine_id, theirs_id = await _setup_two_shops(test_session)

    repo = ShopRepository(test_session)
    their_batch = await repo.create_import_batch(theirs_id, "narxlar.xlsx", total_rows=1)
    await test_session.flush()

    row = ImportRow(
        batch_id=their_batch.id,
        row_no=1,
        raw_payload={"name": "Sement", "price": "52000"},
    )
    test_session.add(row)
    await test_session.flush()

    # The batch's real owner passes; the other owner must not.
    assert await _batch_belongs_to_user(them, test_session, their_batch.id) is True
    assert await _batch_belongs_to_user(me, test_session, their_batch.id) is False

    assert await _row_belongs_to_user(them, test_session, row.id) is True
    assert await _row_belongs_to_user(me, test_session, row.id) is False

    # Ids that do not exist are refused rather than treated as permitted.
    assert await _batch_belongs_to_user(me, test_session, 999999) is False
    assert await _row_belongs_to_user(me, test_session, 999999) is False


@pytest.mark.asyncio
async def test_product_edit_is_scoped_to_the_owning_shop(test_session: AsyncSession) -> None:
    """Product ids come from callback data, so editing must re-check ownership."""
    from decimal import Decimal

    from app.bot.handlers.shop import _load_editable_product
    from app.db.models import ShopProduct

    me, them, mine_id, theirs_id = await _setup_two_shops(test_session)

    their_product = ShopProduct(
        shop_id=theirs_id,
        raw_name="Sement M400",
        raw_unit="qop",
        pack_size=Decimal("1"),
        price_per_pack=Decimal("52000"),
        price_per_base_unit=Decimal("52000"),
    )
    test_session.add(their_product)
    await test_session.flush()

    assert await _load_editable_product(them, test_session, their_product.id) is not None
    assert await _load_editable_product(me, test_session, their_product.id) is None

    # An admin moderates every shop, so they may edit it.
    admin = User(tg_id=777, full_name="Admin", lang="uz_latn", role="admin")
    test_session.add(admin)
    await test_session.flush()
    assert await _load_editable_product(admin, test_session, their_product.id) is not None

    # A product id that does not exist is refused, not treated as permitted.
    assert await _load_editable_product(them, test_session, 999999) is None
