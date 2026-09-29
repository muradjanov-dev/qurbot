"""Run throwaway Tezqur designs with an in-memory DB and no external services.

    .venv/bin/python -m scripts.preview_redesign --port 18082

Open /manage?variant=A, /catalog/all?variant=B, or /chat?variant=C.
All POST/PUT/PATCH/DELETE requests are blocked. UI interactions live in JS memory.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# Override every external connection BEFORE importing the actual application.
os.environ.update(
    {
        "APP_ENV": "local",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "FSM_USE_REDIS": "false",
        "BOT_TOKEN": "123456:PROTOTYPE_NO_REAL_TELEGRAM_TOKEN",
        "REGISTER_WEBHOOK": "false",
        "WEBHOOK_SECRET": "prototype-local-only",
        "TELEGRAM_NOTIFICATIONS_ENABLED": "false",
        "LLM_ENABLED": "false",
        "AGENT_ENABLED": "false",
        "ANTHROPIC_API_KEY": "placeholder_anthropic_key",
        "OPENAI_API_KEY": "placeholder_openai_key",
        "SENTRY_DSN": "",
        "WEB_SESSION_SECRET": "local-prototype-not-production",
        "ADMIN_TG_IDS": "[]",
        "SUPER_ADMIN_TG_IDS": "[]",
        "WEB_DEV_LOGIN_ENABLED": "false",
    }
)

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.models.catalog import CanonicalProduct  # noqa: E402
from app.db.models.shop import ShopProduct  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import async_session_factory, engine  # noqa: E402
from app.domain.normalize.translit import latin_to_cyrillic_uz  # noqa: E402
from app.main import app  # noqa: E402
from app.web.storefront.deps import current_user  # noqa: E402
from scripts.seed import USD_TO_UZS, our_priced_rows, seed_database  # noqa: E402


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        await seed_database(session, catalog_only=True)
        session.add(
            User(id=1, tg_id=990000001, full_name="Demo Admin", role="admin", lang="uz_cyrl")
        )
        await session.commit()
        rows = (
            await session.scalars(
                select(ShopProduct).where(ShopProduct.is_active.is_(True)).order_by(ShopProduct.id)
            )
        ).all()
        source = {slug: amount for slug, amount, _, _ in our_priced_rows()}
        # Existing catalogue values only; pick varied material photos/pack labels.
        chosen = rows[:8] + rows[20:24]
        items: list[dict[str, Any]] = []
        for index, offer in enumerate(chosen):
            product = offer.canonical_product
            assert product is not None
            category = product.category
            source_currency = "USD" if index % 2 == 0 and product.slug in source else "UZS"
            amount = source[product.slug] if source_currency == "USD" else str(offer.price_per_pack)
            items.append(
                {
                    "id": product.id,
                    "names": {
                        "uz_latn": product.name_uz,
                        "uz_cyrl": product.name_uz_cyrl,
                        "ru": product.name_ru,
                    },
                    "categories": {
                        "uz_latn": category.name_uz,
                        "uz_cyrl": latin_to_cyrillic_uz(category.name_uz),
                        "ru": category.name_ru,
                    },
                    "unit": offer.pack_unit_code or product.base_unit_code,
                    "pack_size": format(offer.pack_size.normalize(), "f"),
                    "image_url": product.display_image_url,
                    "source_currency": source_currency,
                    "source_price": amount,
                    "available": offer.stock_status in {"in_stock", "low"},
                    "brand": product.brand or "",
                }
            )
        application.state.design_products = items
        application.state.design_rate = USD_TO_UZS
        application.state.design_stats = {
            "products": await session.scalar(select(func.count(CanonicalProduct.id))),
            "offers": len(rows),
            "orders": 0,
            "customers": 0,
        }
    application.state.design_preview = True
    yield
    await engine.dispose()


async def preview_user(request: Request) -> User | None:
    if request.query_params.get("persona") == "guest" and not request.url.path.startswith(
        "/manage"
    ):
        return None
    async with async_session_factory() as session:
        return await session.get(User, 1)


app.router.lifespan_context = lifespan
app.dependency_overrides[current_user] = preview_user


@app.middleware("http")
async def read_only_preview(request: Request, call_next: Any) -> Any:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse({"detail": "prototype_read_only"}, status_code=405)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Tezqur-Prototype"] = "local-only"
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18082)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
