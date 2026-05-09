from __future__ import annotations

import logging
import re
import sys
from typing import Any

# Secret patterns to scrub from log output
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_.-]+", re.IGNORECASE),
    re.compile(r"api[-_]?key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9_-]+['\"]?", re.IGNORECASE),
]


class SecretScubbingFormatter(logging.Formatter):
    """Logging formatter that scrubs API keys and bearer tokens from logs."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        for pattern in SECRET_PATTERNS:
            formatted = pattern.sub("[REDACTED_SECRET]", formatted)
        return formatted


def setup_logger(name: str = "jarvis", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = SecretScubbingFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()
