"""The customer-facing website.

Same product as the bot, second doorway. A visitor signs in with Telegram, so
the account they land on is the very `users` row the bot writes: the same
orders, the same saved addresses, the same pebbles. Nothing here is a parallel
account system, and nothing here re-implements pricing -- pages call the same
services (`CatalogService`, `QuoteService`) the handlers do.

Kept apart from `app/web/routers/` (the admin panel, SPEC §11) because the two
have opposite audiences and opposite auth: HTTP Basic for operators there,
Telegram identity for customers here.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.web.storefront.routers import account, auth, basket, catalog, checkout, home, orders, shop

STATIC_DIR = Path(__file__).parent / "static"
STATIC_URL = "/static/store"

router = APIRouter()
router.include_router(home.router)
router.include_router(catalog.router)
router.include_router(basket.router)
router.include_router(checkout.router)
router.include_router(orders.router)
router.include_router(account.router)
router.include_router(auth.router)
router.include_router(shop.router)


def install_storefront(app: FastAPI) -> None:
    """Mount the storefront's routes and static assets onto the app."""
    app.mount(STATIC_URL, StaticFiles(directory=str(STATIC_DIR)), name="storefront-static")
    app.include_router(router)


__all__ = ["STATIC_URL", "install_storefront", "router"]
