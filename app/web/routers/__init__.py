from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.web.routers import (
    aliases,
    dashboard,
    listings,
    offers,
    orders,
    products,
    unmatched,
)
from app.web.storefront.security import require_same_origin_write

router = APIRouter(dependencies=[Depends(require_same_origin_write)])


@router.get("/admin")
async def admin_root() -> RedirectResponse:
    return RedirectResponse("/manage")


router.include_router(unmatched.router)
router.include_router(aliases.router)
router.include_router(offers.router)
router.include_router(products.router)
router.include_router(listings.router)
router.include_router(orders.router)
router.include_router(dashboard.router)
