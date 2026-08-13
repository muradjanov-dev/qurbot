from typing import Any

from arq.connections import RedisSettings

from app.bot.dispatcher import create_bot
from app.core.config import settings
from app.core.logging import configure_logging, configure_sentry, get_logger
from app.workers.schedules import CRON_JOBS

logger = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(settings.log_level)
    configure_sentry(settings.sentry_dsn, settings.app_env)
    ctx["bot"] = create_bot()
    logger.info("worker_started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    bot = ctx.get("bot")
    if bot is not None:
        await bot.session.close()
    logger.info("worker_stopped")


class WorkerSettings:
    """arq entrypoint: `arq app.workers.main.WorkerSettings`."""

    cron_jobs = CRON_JOBS
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    handle_signals = True
