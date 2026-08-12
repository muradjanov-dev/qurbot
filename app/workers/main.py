import asyncio

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    configure_logging(settings.log_level)
    logger.info("worker_placeholder_started", note="arq tasks land in Phase 8")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
