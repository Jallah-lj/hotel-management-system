"""Logging configuration.

Emits single-line, structured-ish logs that are friendly to both humans and
log aggregators.  Request logs carry a correlation id that is also returned
to clients in the ``X-Request-ID`` header so support can trace issues.
"""

from __future__ import annotations

import logging
import sys
import time
from contextvars import ContextVar

from app.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_ctx.get("-")
        return True


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41m",
    }
    RESET = "\033[0m"

    def __init__(self, *args, use_color: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self.use_color:
            return message
        color = self.COLORS.get(record.levelname, "")
        return f"{color}{message}{self.RESET}" if color else message


def configure_logging() -> None:
    use_color = sys.stderr.isatty() and not settings.is_production
    formatter = ColorFormatter(
        fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        use_color=use_color,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    # Tame noisy third-party loggers.
    for noisy in ("uvicorn.access", "sqlalchemy.engine.Engine", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING if not settings.sql_echo else logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class Timer:
    """Small helper used by request middleware and service timings."""

    def __init__(self) -> None:
        self.start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.start) * 1000, 2)
