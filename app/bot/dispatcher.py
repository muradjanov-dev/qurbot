import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.bot.handlers import (
    admin_router,
    ai_chat_router,
    common_router,
    customer_router,
    fallback_router,
    price_browse_router,
    shop_listing_router,
    shop_router,
)
from app.bot.handlers.operator import router as operator_router
from app.bot.middlewares import (
    DbSessionMiddleware,
    ErrorMiddleware,
    I18nMiddleware,
    LoggingMiddleware,
    ThrottleMiddleware,
    UserContextMiddleware,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


def create_storage() -> BaseStorage:
    """Build the FSM storage.

    Redis keeps multi-step wizard state alive across restarts and lets more than
    one web replica serve the same user. Falling back to MemoryStorage is only
    ever a local-dev convenience: durable data (listing drafts, uploaded photos)
    is written to Postgres as it is collected, never held solely in FSM state.
    """
    if not settings.fsm_use_redis:
        return MemoryStorage()
    try:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.redis_url)
    except Exception:
        logger.warning(
            "redis_fsm_unavailable_falling_back_to_memory url=%s", settings.redis_url, exc_info=True
        )
        return MemoryStorage()


def create_bot() -> Bot:
    """Create and configure aiogram Bot instance."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def setup_bot_commands(bot: Bot) -> None:
    """Register native Telegram bot menu commands."""
    commands = [
        BotCommand(command="start", description="Boshlash / Menyu"),
        BotCommand(command="menu", description="Asosiy menyu tugmalarini chiqarish"),
        BotCommand(command="orders", description="Mening buyurtmalarim"),
        BotCommand(command="settings", description="Sozlamalar"),
        BotCommand(command="reregister", description="0 dan qayta ro'yxatdan o'tish"),
        BotCommand(command="cancel", description="Amalni bekor qilish"),
        BotCommand(command="shop_products", description="Mahsulotlar ro'yxati (adminlar)"),
        BotCommand(command="delivery_rules", description="Yetkazish qoidalari (adminlar)"),
    ]
    with suppress(Exception):
        await bot.set_my_commands(commands)


def create_dispatcher() -> Dispatcher:
    """Factory function creating and configuring Dispatcher with middlewares and routers."""
    dp = Dispatcher(storage=create_storage())

    # Middlewares registered in exact order according to SPEC §9:
    # ErrorMiddleware -> LoggingMiddleware -> ThrottleMiddleware ->
    # DbSessionMiddleware -> UserContextMiddleware -> I18nMiddleware

    # Outer middlewares
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(LoggingMiddleware())
    dp.update.outer_middleware(
        ThrottleMiddleware(
            limit_per_minute=settings.throttle_limit_per_minute,
            quote_limit_per_minute=settings.throttle_quote_limit_per_minute,
        )
    )
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserContextMiddleware())
    dp.update.outer_middleware(I18nMiddleware())

    # Include routers. shop_listing_router goes first because its handlers are
    # all state-filtered to the upload wizard, while customer_router's basket
    # handlers match loose text that would otherwise swallow a wizard step
    # (cf. commit e68f17c).
    dp.include_router(common_router)
    dp.include_router(shop_listing_router)
    dp.include_router(price_browse_router)
    # shop_router precedes customer_router: inside the admin quick-price and
    # delivery-rule states ("cement m400 52000") the text is ordinary, so the
    # basket catch-all would otherwise consume it.
    dp.include_router(shop_router)
    dp.include_router(operator_router)
    # The AI sales agent answers customer free text first; with no key it
    # filters itself out and the basket handler in customer_router runs.
    dp.include_router(ai_chat_router)
    dp.include_router(customer_router)
    dp.include_router(admin_router)
    # Last: whatever no handler claimed still gets an answer. Registered
    # here so it can never shadow a real handler -- it only ever sees what
    # fell all the way through.
    dp.include_router(fallback_router)

    return dp


dispatcher = create_dispatcher()
