"""Application logging: rotating file + console, with secret scrubbing.

Named ``logsetup`` (not ``logging``) so it never shadows the stdlib module.
All app loggers are children of the ``jarvis`` root logger.
"""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from .config.paths import LOG_DIR, ensure_dirs

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_.-]+", re.IGNORECASE),
    re.compile(r"api[-_]?key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9_-]+", re.IGNORECASE),
]

_configured = False


class _ScrubbingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = super().format(record)
        for pat in _SECRET_PATTERNS:
            out = pat.sub("[REDACTED]", out)
        return out


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the ``jarvis`` root logger once (idempotent)."""
    global _configured
    if _configured:
        return
    ensure_dirs()

    root = logging.getLogger("jarvis")
    root.setLevel(level)
    root.propagate = False

    fmt = _ScrubbingFormatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        fileh = RotatingFileHandler(
            LOG_DIR / "jarvis.log", maxBytes=2_000_000, backupCount=5,
            encoding="utf-8",
        )
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
    except OSError:
        # File logging is best-effort; console still works.
        pass

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger, e.g. ``get_logger("runner")``."""
    return logging.getLogger(f"jarvis.{name}")
