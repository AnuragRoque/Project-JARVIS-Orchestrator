"""Launch-on-login toggle via the per-user Run registry key (no admin needed).

Kept minimal here; Phase 8 (packaging) replaces the ``python -m jarvis`` command
with the packaged executable. Uses ``pythonw`` when available so no console
window flashes on login.
"""
from __future__ import annotations

import os
import sys

from .logsetup import get_logger

log = get_logger("autostart")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "JARVIS"


def _launch_command() -> str:
    exe = sys.executable or "python"
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" -m jarvis'


def set_autostart(enabled: bool) -> bool:
    """Add or remove the login entry. Returns True on success."""
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, _launch_command())
                log.info("Autostart enabled")
            else:
                try:
                    winreg.DeleteValue(key, _NAME)
                    log.info("Autostart disabled")
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Failed to update autostart entry")
        return False


def is_autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _NAME)
        return True
    except (ImportError, OSError):
        return False
