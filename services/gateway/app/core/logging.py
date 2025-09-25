import logging
from typing import Any, Dict

import structlog


def _configure_stdlib_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )


def configure_structlog() -> None:
    _configure_stdlib_logging()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
