"""
Logging configuration
"""

import logging
import sys
from pathlib import Path

try:
    from loguru import logger as loguru_logger
except Exception:  # pragma: no cover - optional dependency
    loguru_logger = None

from app.core.config import settings


class _FallbackLogger:
    """A tiny adapter that mimics the subset of loguru used by this project."""

    def __init__(
        self, std_logger: logging.Logger, extra: dict | None = None, exc: Exception | None = None
    ):
        self._std = std_logger
        self._extra = extra or {}
        self._exc = exc
        self.level = settings.LOG_LEVEL.upper()

    def _render(self, message: str, args: tuple) -> str:
        if not args:
            return str(message)
        try:
            return str(message).format(*args)
        except Exception:
            try:
                return str(message) % args
            except Exception:
                return f"{message} {' '.join(str(a) for a in args)}"

    def _with_context(self, message: str) -> str:
        if not self._extra:
            return message
        ctx = " ".join(f"{k}={v}" for k, v in self._extra.items())
        return f"{message} | {ctx}"

    def bind(self, **kwargs):
        merged = dict(self._extra)
        merged.update(kwargs)
        return _FallbackLogger(self._std, merged, self._exc)

    def opt(self, exception=None, **kwargs):
        return _FallbackLogger(self._std, dict(self._extra), exception or self._exc)

    def debug(self, message, *args):
        self._std.debug(self._with_context(self._render(message, args)), exc_info=self._exc)

    def info(self, message, *args):
        self._std.info(self._with_context(self._render(message, args)), exc_info=self._exc)

    def warning(self, message, *args):
        self._std.warning(self._with_context(self._render(message, args)), exc_info=self._exc)

    def error(self, message, *args):
        self._std.error(self._with_context(self._render(message, args)), exc_info=self._exc)

    def exception(self, message, *args):
        self._std.exception(self._with_context(self._render(message, args)))


class InterceptHandler(logging.Handler):
    """
    Intercept standard logging messages and redirect to loguru
    """

    def emit(self, record):
        if loguru_logger is None:
            logging.getLogger(record.name).handle(record)
            return

        # Get corresponding Loguru level if it exists
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging():
    """
    Setup application logging with loguru
    """
    if loguru_logger is None:
        logging.basicConfig(
            level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
            format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            stream=sys.stdout,
            force=True,
        )
        return _FallbackLogger(logging.getLogger("clothing_assistant"))

    # Remove default logger
    loguru_logger.remove()

    # Add console handler
    # colorize=True emits ANSI escape codes — disable in non-TTY (PowerShell)
    # so they don't show up as garbled characters like [32m [1m [0m [36m
    import os
    import sys

    colorize = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    loguru_logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=settings.LOG_LEVEL,
        colorize=colorize,
    )

    # Add file handler
    log_file = Path(settings.LOG_FILE)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    loguru_logger.add(
        settings.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
    )

    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Intercept uvicorn logs
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]

    return loguru_logger
