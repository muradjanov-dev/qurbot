from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.common import router as common_router
from app.bot.handlers.customer import router as customer_router
from app.bot.handlers.shop import router as shop_router

__all__ = [
    "admin_router",
    "common_router",
    "customer_router",
    "shop_router",
]
