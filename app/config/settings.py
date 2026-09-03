"""Global application settings (JSON-backed).

Holds cross-cutting preferences (permission mode, wake words, theme, startup).
Per-module settings live in their own namespace files under
``%LOCALAPPDATA%\\Jarvis\\modules\\<id>.json`` via :class:`ModuleSettings`.
Secrets (API keys/tokens) stay in each module's ``.env`` — never here.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from .paths import CONFIG_PATH, MODULES_CONFIG_DIR, ensure_dirs

DEFAULTS: dict[str, Any] = {
    "permission_mode": "partial",        # auto | partial | manual
    "wake_words": ["jarvis"],            # multiple supported (Phase 5 always-on)
    "require_wake_word": False,
    "theme": "blue",                     # global theme key (see ui/theme.py)
    "start_minimized": False,            # start into the tray only
    "autostart": False,                  # launch on Windows login (Phase 8)
    "float_pos": None,                   # remembered orb position [x, y]
    "float_size": [400, 600],            # remembered orb card size [w, h]
    "dim_when_idle": True,               # fade the floating window when unhovered
    "tab_order": [
        "voice", "timeline", "terminal", "logs", "settings", "dashboard",
    ],
}


class _JsonStore:
    """A JSON file holding a flat dict, with defaults and atomic writes."""

    def __init__(self, path, defaults: dict[str, Any] | None = None) -> None:
        ensure_dirs()
        self._path = path
        self._defaults = dict(defaults or {})
        self._lock = threading.RLock()
        self._data = dict(self._defaults)
        if path.exists():
            try:
                self._data.update(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        else:
            # Materialise defaults on first run so the file is inspectable.
            self._save()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, self._defaults.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)
            self._save()

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def _save(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        tmp.replace(self._path)


class GlobalSettings(_JsonStore):
    def __init__(self) -> None:
        super().__init__(CONFIG_PATH, DEFAULTS)


class ModuleSettings(_JsonStore):
    """Per-module settings namespace, persisted to ``modules/<id>.json``."""

    def __init__(self, module_id: str, defaults: dict[str, Any] | None = None) -> None:
        super().__init__(MODULES_CONFIG_DIR / f"{module_id}.json", defaults)


_settings: GlobalSettings | None = None
_lock = threading.Lock()


def get_settings() -> GlobalSettings:
    global _settings
    with _lock:
        if _settings is None:
            _settings = GlobalSettings()
        return _settings
