import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram.exceptions import TelegramAPIError
from fastapi import FastAPI

from app.api.routers import health, metrics, webhook
from app.bot.dispatcher import create_bot, dispatcher, setup_bot_commands
from app.core.config import settings
from app.core.deploy_notify import notify_admins_of_deploy
from app.core.logging import configure_logging, configure_sentry, get_logger
from app.web.routers import router as admin_router
from app.web.storefront import install_storefront

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    configure_sentry(settings.sentry_dsn, settings.app_env)

    bot = create_bot()
    app.state.bot = bot
    app.state.dispatcher = dispatcher
    await setup_bot_commands(bot)

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

        # Gated on register_webhook (a proxy for "this is a real deployment, not
        # local dev"). Fires on every container start in that environment -- not
        # just genuine new deploys -- since Railway's preDeployCommand phase has
        # unreliable outbound networking for this call in practice, while this
        # startup path is proven reliable (same context as setWebhook above).
        release_label = os.environ.get("RAILWAY_DEPLOYMENT_ID", "local")
        await notify_admins_of_deploy(bot, release_label)

    yield

    # Deliberately does NOT call bot.delete_webhook() here. Railway's deploys are
    # rolling: the new container sets the webhook and starts serving before the
    # old one shuts down, so an unconditional delete-on-shutdown here would race
    # and delete the *new* container's registration moments after it was set --
    # which is exactly what was happening (webhook silently going empty after
    # every deploy). Startup already re-registers idempotently every boot, so
    # there's nothing for shutdown to clean up.
    await bot.session.close()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(title="QurBot", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(webhook.router)
    app.include_router(metrics.router)
    app.include_router(admin_router)
    if settings.web_enabled:
        # The customer-facing site. Mounted last so its "/" never shadows the
        # webhook, health or admin routes above.
        install_storefront(app)
    return app


app = create_app()
