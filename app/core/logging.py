import logging
from typing import Any

import sentry_sdk
import structlog


def configure_sentry(dsn: str | None, environment: str) -> None:
    """No-op unless a DSN is configured -- Sentry needs the operator's own project."""
    if not dsn:
        return
    sentry_sdk.init(dsn=dsn, environment=environment, send_default_pii=False)


def configure_logging(log_level: str) -> None:
    logging.basicConfig(format="%(message)s", level=log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
