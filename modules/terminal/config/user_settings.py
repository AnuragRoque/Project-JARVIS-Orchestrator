from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jarvis.modules.terminal.core.logging import logger

BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_PATH = BASE_DIR / "user_settings.json"

# Default UI/session preferences. Only keys listed here are persisted/loaded,
# so an unknown or stale key in the JSON file is ignored safely.
DEFAULTS: dict[str, Any] = {
    "provider": "Ollama",          # "Ollama" | "ChatGPT"
    "mode": "Partial",             # "Manual" | "Partial" | "Auto"
    "model": "",                   # last selected model name
    "terminal_power": True,        # 🔧 Terminal power
    "use_saved_commands": True,    # ⚡ Use saved commands
    "show_steps": False,           # 🔍 Show steps
}


class UserSettings:
    """Small JSON-backed store for user UI preferences that survive restarts."""

    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    # Only accept known keys to keep the shape stable.
                    self._data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Could not read {self.path.name}, using defaults: {exc}")
        return self._data

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Could not write {self.path.name}: {exc}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value: Any) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self.save()

    def update(self, **kwargs: Any) -> None:
        changed = False
        for key, value in kwargs.items():
            if self._data.get(key) != value:
                self._data[key] = value
                changed = True
        if changed:
            self.save()


# Shared singleton used across the UI.
user_settings = UserSettings()
