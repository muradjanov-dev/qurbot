from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

SECRET_HEADER = "x-telegram-bot-api-secret-token"


@router.post(settings.webhook_path)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias=SECRET_HEADER),
) -> dict[str, bool]:
    if (
        x_telegram_bot_api_secret_token is not None
        and x_telegram_bot_api_secret_token != settings.webhook_secret
    ):
        raise HTTPException(status_code=403, detail="invalid secret token")

    body = await request.json()
    update = Update.model_validate(body)

    bot = request.app.state.bot
    dispatcher = request.app.state.dispatcher
    if bot is None or dispatcher is None:
        raise HTTPException(status_code=503, detail="bot not ready")

    await dispatcher.feed_webhook_update(bot, update)
    return {"ok": True}
