"""End-to-end coverage for the shop product upload path.

The tests that matter most here are the durability ones: an interrupted upload
must be resumable with nothing re-typed, and an uploaded photo must survive the
Telegram file_id it arrived with going stale.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog import CanonicalProduct, Category, Unit
from app.db.models.shop import District, ProductPhotoBlob, Shop, ShopProduct
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.listing_repo import ListingRepository, draft_to_domain
from app.db.repositories.ops_repo import OpsRepository
from app.domain.listing import PhotoRef, next_missing_step, parse_listing_caption
from app.services.listing_service import ListingService


async def _fixture_shop(session: AsyncSession) -> Shop:
    session.add_all(
        [
            Unit(code="kg", name_uz="kilogramm", name_ru="килограмм", dimension="mass"),
            Unit(code="dona", name_uz="dona", name_ru="штука", dimension="count"),
        ]
    )
    category = Category(slug="sement", name_uz="Sement", name_ru="Цемент", sort_order=1)
    district = District(region="Toshkent", name_uz="Chilonzor", name_ru="Чиланзар")
    session.add_all([category, district])
    await session.flush()

    session.add(
        CanonicalProduct(
            slug="sement-m400",
            name_uz="Sement M400",
            name_uz_cyrl="Семент М400",
            name_ru="Цемент М400",
            brand="Qizilqum",
            category_id=category.id,
            base_unit_code="kg",
            attributes={"grade": "M400"},
            search_doc="sement m400 cement qizilqum",
            tier="standard",
            is_active=True,
        )
    )
    shop = Shop(
        name="Test Shop",
        phone="+998900000000",
        owner_tg_id=555001,
        district_id=district.id,
        address="Test ko'chasi 1",
    )
    session.add(shop)
    await session.flush()
    return shop


def _service(session: AsyncSession) -> ListingService:
    return ListingService(
        session,
        ListingRepository(session),
        CatalogRepository(session),
        OpsRepository(session),
    )


@pytest.mark.asyncio
async def test_caption_creates_a_comparable_offer(test_session: AsyncSession) -> None:
    """A one-line caption becomes a live offer priced per base unit."""
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)

    draft = await repo.create_draft(shop.id, 555001)
    parsed = parse_listing_caption("Sement M400 50kg qop 52000 so'm")
    await repo.update_draft(
        draft,
        name=parsed.name,
        pack_size=parsed.pack_size,
        pack_unit_code=parsed.pack_unit,
        price_per_pack=parsed.price,
    )

    outcome = await _service(test_session).apply_draft(draft)
    await test_session.commit()

    product = await test_session.get(ShopProduct, outcome.shop_product_id)
    assert product is not None
    assert product.price_per_pack == Decimal("52000.00")
    # 52,000 for a 50 kg bag is 1,040/kg -- the figure every quote compares on.
    assert product.price_per_base_unit == Decimal("1040.0000")
    assert product.canonical_id is not None, "should have matched the seeded SKU"
    assert product.is_active is True
    assert product.staleness_state == "fresh"


@pytest.mark.asyncio
async def test_listing_without_media_is_not_held_for_moderation(
    test_session: AsyncSession,
) -> None:
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)
    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(
        draft,
        name="Sement M400",
        pack_size=Decimal("50"),
        pack_unit_code="kg",
        price_per_pack=Decimal("52000"),
    )

    outcome = await _service(test_session).apply_draft(draft)
    await test_session.commit()

    product = await test_session.get(ShopProduct, outcome.shop_product_id)
    assert product is not None
    assert product.moderation_status == "approved"
    assert outcome.media_pending is False


@pytest.mark.asyncio
async def test_photos_hold_media_for_review_but_not_the_price(
    test_session: AsyncSession,
) -> None:
    """Unreviewed photos must not block the offer from competing in quotes."""
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)
    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(
        draft,
        name="Sement M400",
        pack_size=Decimal("50"),
        pack_unit_code="kg",
        price_per_pack=Decimal("52000"),
    )
    await repo.append_photo(draft, PhotoRef(file_id="f1", file_unique_id="u1", pos=0))

    outcome = await _service(test_session).apply_draft(draft)
    await test_session.commit()

    product = await test_session.get(ShopProduct, outcome.shop_product_id)
    assert product is not None
    assert product.moderation_status == "pending"
    assert product.is_active is True, "a pending photo must not deactivate a real price"
    assert product.staleness_state == "fresh"


@pytest.mark.asyncio
async def test_pending_media_is_hidden_from_customers_but_shown_to_owner(
    test_session: AsyncSession,
) -> None:
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)
    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(
        draft,
        name="Sement M400",
        pack_size=Decimal("50"),
        pack_unit_code="kg",
        price_per_pack=Decimal("52000"),
    )
    await repo.append_photo(draft, PhotoRef(file_id="f1", file_unique_id="u1", pos=0))
    service = _service(test_session)
    outcome = await service.apply_draft(draft)
    await test_session.commit()

    product = await test_session.get(ShopProduct, outcome.shop_product_id)
    assert product is not None

    customer_card = await service.build_card(product, viewer_is_owner=False)
    owner_card = await service.build_card(product, viewer_is_owner=True)

    assert customer_card.photos == (), "unreviewed media must not reach a customer"
    assert owner_card.has_photos is True, "the owner must see their upload landed"
    # The product itself still renders for the customer -- only media is withheld.
    assert customer_card.price_per_pack == Decimal("52000.00")
    # White-label: a customer card must never carry the supplying shop.
    assert customer_card.shop_name is None
    assert owner_card.shop_name == "Test Shop"


@pytest.mark.asyncio
async def test_interrupted_upload_resumes_without_retyping(
    test_session: AsyncSession,
) -> None:
    """Simulates losing the session mid-upload: the draft is found by owner."""
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)

    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(draft, name="Sement M400", pack_size=Decimal("50"), pack_unit_code="kg")
    await test_session.commit()

    # ... bot restarts, FSM state is gone entirely ...
    recovered = await repo.get_open_draft(555001)
    assert recovered is not None
    assert recovered.id == draft.id
    assert recovered.name == "Sement M400"
    assert recovered.pack_size == Decimal("50.0000")

    # And it knows to ask for the price rather than starting over.
    from app.domain.listing import ListingStep

    assert next_missing_step(draft_to_domain(recovered)) is ListingStep.PRICE


@pytest.mark.asyncio
async def test_photo_bytes_are_stored_independently_of_the_file_id(
    test_session: AsyncSession,
) -> None:
    """The blob is the store of record: a rotated bot token invalidates file_ids."""
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)

    await repo.store_photo_blob(
        file_unique_id="stable-id",
        file_id="old-file-id",
        data=b"\xff\xd8\xff-jpeg-bytes",
        shop_id=shop.id,
    )
    await test_session.commit()

    blob = await repo.get_photo_blob("stable-id")
    assert blob is not None
    assert blob.data == b"\xff\xd8\xff-jpeg-bytes"
    assert blob.byte_size == len(b"\xff\xd8\xff-jpeg-bytes")

    # Re-uploading the same image refreshes the handle without duplicating bytes.
    await repo.store_photo_blob(
        file_unique_id="stable-id", file_id="new-file-id", data=b"ignored", shop_id=shop.id
    )
    await test_session.commit()

    rows = (await test_session.execute(select(ProductPhotoBlob))).scalars().all()
    assert len(rows) == 1
    assert rows[0].file_id == "new-file-id"
    assert rows[0].data == b"\xff\xd8\xff-jpeg-bytes"


@pytest.mark.asyncio
async def test_relisting_updates_the_offer_instead_of_duplicating(
    test_session: AsyncSession,
) -> None:
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)
    service = _service(test_session)

    first = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(
        first,
        name="Sement M400",
        pack_size=Decimal("50"),
        pack_unit_code="kg",
        price_per_pack=Decimal("52000"),
    )
    await service.apply_draft(first)
    await test_session.commit()

    second = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(
        second,
        name="Sement M400",
        pack_size=Decimal("50"),
        pack_unit_code="kg",
        price_per_pack=Decimal("55000"),
    )
    await service.apply_draft(second)
    await test_session.commit()

    offers = (
        (await test_session.execute(select(ShopProduct).where(ShopProduct.shop_id == shop.id)))
        .scalars()
        .all()
    )
    assert len(offers) == 1, "same product and pack must update in place"
    assert offers[0].price_per_pack == Decimal("55000.00")


@pytest.mark.asyncio
async def test_incomplete_draft_is_refused(test_session: AsyncSession) -> None:
    """A draft missing its price must never reach shop_products."""
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)
    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(draft, name="Sement M400", pack_size=Decimal("50"), pack_unit_code="kg")

    with pytest.raises(ValueError):
        await _service(test_session).apply_draft(draft)


@pytest.mark.asyncio
async def test_album_photos_attach_to_the_same_draft(test_session: AsyncSession) -> None:
    """Album members arrive as separate updates; they must not create separate drafts."""
    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)

    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(draft, media_group_id="album-42", name="Sement M400")
    await test_session.commit()

    found = await repo.get_draft_by_media_group(555001, "album-42")
    assert found is not None
    assert found.id == draft.id

    for i in range(3):
        await repo.append_photo(found, PhotoRef(file_id=f"f{i}", file_unique_id=f"u{i}", pos=i))
    await test_session.commit()

    assert len(found.photos) == 3


@pytest.mark.asyncio
async def test_unmatched_listing_is_queued_for_the_catalog(
    test_session: AsyncSession,
) -> None:
    """A product we don't know must grow the catalogue, not vanish."""
    from app.db.models.ops import UnmatchedQuery

    shop = await _fixture_shop(test_session)
    repo = ListingRepository(test_session)
    draft = await repo.create_draft(shop.id, 555001)
    await repo.update_draft(
        draft,
        name="Xitoy fanera nostandart",
        pack_size=Decimal("1"),
        pack_unit_code="dona",
        price_per_pack=Decimal("95000"),
    )

    outcome = await _service(test_session).apply_draft(draft)
    await test_session.commit()

    assert outcome.canonical_id is None
    unmatched = (await test_session.execute(select(UnmatchedQuery))).scalars().all()
    assert len(unmatched) >= 1
