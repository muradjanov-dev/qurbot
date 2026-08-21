"""Everything that must happen before a new version takes traffic.

Two steps: bring the schema up to head, then roll out catalogue changes.

This exists as one Python entry point rather than a shell one-liner because
Railway's ``preDeployCommand`` does not run its entry through a shell -- an
``&&`` between two commands is silently not executed, so the first command runs,
the second never does, and the deploy still reports success. That failure mode
is invisible: migrations applied, catalogue quietly stale. Doing both steps in
one process removes the shell from the picture and makes a failure in either
step fail the deploy.

Usage: python -m scripts.predeploy
"""

import asyncio
import logging
import pathlib
import sys

from alembic import command
from alembic.config import Config

from app.db.session import async_session_factory
from scripts.seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("predeploy")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def run_migrations() -> None:
    logger.info("predeploy: alembic upgrade head")
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")
    logger.info("predeploy: migrations done")


async def run_catalog_seed() -> None:
    """Roll out catalogue changes without touching the live marketplace.

    catalog_only stops before shops, offers and demo users, so new products
    become matchable without re-creating placeholder shops next to real ones.
    """
    logger.info("predeploy: seeding catalogue (catalog_only)")
    async with async_session_factory() as session:
        await seed_database(session, catalog_only=True)
        await session.commit()
    logger.info("predeploy: catalogue seed done")


def main() -> int:
    try:
        run_migrations()
        asyncio.run(run_catalog_seed())
    except Exception:
        # Fail loudly: a half-applied predeploy must stop the rollout rather
        # than let a new version serve against a stale schema or catalogue.
        logger.exception("predeploy failed")
        return 1
    logger.info("predeploy: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
