"""loguru bootstrap.

Call `configure_logging()` once at process start (from each entrypoint).
"""

from __future__ import annotations

import logging
import sys

from loguru import logger

from shared.config import get_settings

_CONFIGURED = False


class _InterceptHandler(logging.Handler):
    """Route stdlib `logging` records into loguru so library logs share format."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        backtrace=False,
        diagnose=settings.app_env != "production",
        enqueue=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    # Bridge stdlib logging (telethon, aiogram, sqlalchemy, etc.).
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "telethon", "aiogram", "apscheduler", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [_InterceptHandler()]
        logging.getLogger(name).propagate = False

    _CONFIGURED = True
