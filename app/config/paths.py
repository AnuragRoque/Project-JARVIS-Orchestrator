"""Filesystem locations for the unified app.

All persistent runtime data lives under ``%LOCALAPPDATA%\\Jarvis`` (falling back
to ``~/.jarvis`` off-Windows). Existing per-module data (e.g. the timeline's
``activity.db``) keeps its own location for now — see docs/ARCHITECTURE.md
(data-layer, "option A").
"""
from __future__ import annotations

import os
from pathlib import Path


def _base() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "Jarvis"
    return Path.home() / ".jarvis"


DATA_DIR = _base()
DB_PATH = DATA_DIR / "jarvis.db"
CONFIG_PATH = DATA_DIR / "config.json"
MODULES_CONFIG_DIR = DATA_DIR / "modules"
LOG_DIR = DATA_DIR / "logs"


def ensure_dirs() -> None:
    """Create the data directories if they do not yet exist."""
    for p in (DATA_DIR, MODULES_CONFIG_DIR, LOG_DIR):
        p.mkdir(parents=True, exist_ok=True)
