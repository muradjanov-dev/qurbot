"""Public chat and a separate, verified-admin-only operator inbox."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.db.models.user import User
from app.services.house_shop import is_admin
from app.web.storefront.deps import current_lang, current_user, render

router = APIRouter(tags=["storefront"])


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    return render(request, "chat.html", user=user, lang=lang)


@router.get("/operator", response_class=HTMLResponse)
async def operator_page(
    request: Request,
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> Response:
    if user is None or user.tg_id is None:
        target = "/operator"
        conversation = request.query_params.get("conversation", "")
        if conversation.isdigit():
            target += "?conversation=" + conversation
        return RedirectResponse("/login?next=" + quote(target, safe="/"), status_code=303)
    if not is_admin(user):
        raise HTTPException(403, "admin_required")
    return render(request, "operator.html", user=user, lang=lang)
