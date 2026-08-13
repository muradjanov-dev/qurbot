from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.web.routers import aliases, dashboard, offers, orders, shops, unmatched

router = APIRouter()


@router.get("/admin")
async def admin_root() -> RedirectResponse:
    return RedirectResponse("/admin/unmatched")


router.include_router(unmatched.router)
router.include_router(aliases.router)
router.include_router(shops.router)
router.include_router(offers.router)
router.include_router(orders.router)
router.include_router(dashboard.router)
