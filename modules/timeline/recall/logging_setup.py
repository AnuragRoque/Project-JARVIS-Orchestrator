"""Centralised logging configuration with rotating file handler."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from .config import LOG_DIR

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("recall")
    root.setLevel(level)
    root.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "recall.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    if not _configured:
        setup_logging()
    return logging.getLogger(f"recall.{name}")
