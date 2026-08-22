"""Landing page, language switching, and product imagery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.shop_repo import ShopRepository
from app.db.session import get_db_session
from app.web.storefront.deps import current_lang, current_user, render, safe_next
from app.web.storefront.session import LANG_COOKIE, normalize_lang

router = APIRouter(tags=["storefront"])


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    categories = await CatalogRepository(session).list_root_categories()
    return render(request, "home.html", user=user, lang=lang, categories=categories)


@router.get("/lang/{code}")
async def set_language(
    code: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(current_user),
) -> RedirectResponse:
    """Switch language, and remember it on the account when there is one.

    Writing it back to `users.lang` is the point: the choice made on the site
    is the same choice the bot honours on the next message.
    """
    chosen = normalize_lang(code)
    target = safe_next(request.query_params.get("next"))
    response = RedirectResponse(target, status_code=303)
    if chosen is None:
        return response

    response.set_cookie(
        LANG_COOKIE,
        chosen,
        max_age=settings.web_session_max_age_days * 86400,
        httponly=False,
        samesite="lax",
    )
    if user is not None and user.lang != chosen:
        user.lang = chosen
        await session.flush()
    return response


@router.get("/media/product/{canonical_id}")
async def product_image(
    canonical_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """A photo for a catalogue product.

    Prefers a real photo a shop owner uploaded and an admin approved, and falls
    back to the catalogue's own illustration. Only the stored bytes are served:
    a Telegram `file_id` means nothing to a browser.
    """
    product = await CatalogRepository(session).get(canonical_id)
    if product is None:
        return Response(status_code=404)

    photo = await ShopRepository(session).get_photo_for_canonical(canonical_id)
    if photo is not None and photo[1]:
        return Response(
            content=photo[1],
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    return RedirectResponse(product.display_image_url, status_code=302)
