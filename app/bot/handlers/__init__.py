from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.common import router as common_router
from app.bot.handlers.customer import router as customer_router
from app.bot.handlers.fallback import router as fallback_router
from app.bot.handlers.price_browse import router as price_browse_router
from app.bot.handlers.shop import router as shop_router
from app.bot.handlers.shop_listing import router as shop_listing_router

__all__ = [
    "admin_router",
    "common_router",
    "customer_router",
    "fallback_router",
    "price_browse_router",
    "shop_listing_router",
    "shop_router",
]
