"""Chat doorway; guests see a sign-in prompt rather than a broken composer."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.db.models.user import User
from app.web.storefront.deps import current_lang, current_user, render

router = APIRouter(tags=["storefront"])


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    user: User | None = Depends(current_user),
    lang: str = Depends(current_lang),
) -> HTMLResponse:
    return render(request, "chat.html", user=user, lang=lang)
