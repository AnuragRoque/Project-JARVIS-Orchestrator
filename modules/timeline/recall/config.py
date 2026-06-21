"""Application configuration and paths.

All persistent user data lives under %LOCALAPPDATA%\\WindowsActivityRecall by
default. Configuration is stored as JSON so the user (and the Settings UI) can
inspect and edit it. Sensible defaults are provided for everything.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


def _default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / "WindowsActivityRecall"


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "activity.db"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_DIR = DATA_DIR / "logs"


@dataclass
class Config:
    """User-configurable settings with defaults."""

    # Capture
    poll_interval_seconds: float = 2.0
    # Titles matching (case-insensitive substring) any of these are ignored.
    ignore_empty_titles: bool = True
    min_session_seconds: float = 1.0  # discard sessions shorter than this
    # A gap larger than this (same window) still counts as one merged session.
    session_merge_gap_seconds: float = 30.0
    # After this many seconds of no input, stop counting active time.
    idle_timeout_seconds: float = 180.0

    # Privacy / control
    tracking_enabled: bool = True
    browser_tracking_enabled: bool = True
    semantic_indexing_enabled: bool = False
    private_mode: bool = False  # when True, nothing is persisted
    excluded_processes: list[str] = field(default_factory=list)  # e.g. ["KeePass.exe"]
    excluded_domains: list[str] = field(default_factory=list)     # e.g. ["mybank.com"]
    retention_days: int = 0  # 0 = keep forever; else purge older records

    # Local API (browser extension)
    api_host: str = "127.0.0.1"
    api_port: int = 8123

    # UI
    dark_mode: bool = True
    start_minimized: bool = True

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except (json.JSONDecodeError, OSError):
            return cls()
        # Only keep known fields to survive schema changes.
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# A process-wide singleton config, guarded for thread-safe reload/save.
_lock = threading.RLock()
_current: Config | None = None


def get_config() -> Config:
    global _current
    with _lock:
        if _current is None:
            _current = Config.load()
        return _current


def update_config(**changes: Any) -> Config:
    """Apply changes to the live config and persist them."""
    global _current
    with _lock:
        cfg = get_config()
        for key, value in changes.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        cfg.save()
        return cfg


def reload_config() -> Config:
    global _current
    with _lock:
        _current = Config.load()
        return _current
