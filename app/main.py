from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram.exceptions import TelegramAPIError
from fastapi import FastAPI

from app.api.routers import health, metrics, webhook
from app.bot.dispatcher import create_bot, dispatcher
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.web.routers import router as admin_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)

    bot = create_bot()
    app.state.bot = bot
    app.state.dispatcher = dispatcher

    if settings.register_webhook:
        try:
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
                drop_pending_updates=True,
            )
            logger.info("webhook_set", url=settings.webhook_url)
        except TelegramAPIError as exc:
            # Expected in local dev with a placeholder BOT_TOKEN / non-public URL.
            # /health and a synthetic POST to the webhook route still work without this.
            logger.warning("webhook_set_failed", error=str(exc))

    yield

    if settings.register_webhook:
        try:
            await bot.delete_webhook()
        except TelegramAPIError as exc:
            logger.warning("webhook_delete_failed", error=str(exc))
    await bot.session.close()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(title="QurBot", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(webhook.router)
    app.include_router(metrics.router)
    app.include_router(admin_router)
    return app


app = create_app()
