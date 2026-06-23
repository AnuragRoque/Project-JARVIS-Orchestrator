"""Foreground window inspection using the Win32 API.

This module is a thin, side-effect-free wrapper: it returns a snapshot of the
currently active window. All merging/session logic lives in
``tracker_service`` so this stays trivially testable.
"""
from __future__ import annotations

from dataclasses import dataclass

import psutil

try:
    import win32gui
    import win32process
    import win32api
    _HAVE_WIN32 = True
except ImportError:  # allow import on non-Windows for tooling/tests
    _HAVE_WIN32 = False

from ..logging_setup import get_logger

log = get_logger("capture.window")

# Known browser process names -> canonical browser label.
BROWSER_PROCESSES = {
    "chrome.exe": "chrome",
    "msedge.exe": "edge",
    "firefox.exe": "firefox",
    "brave.exe": "brave",
    "opera.exe": "opera",
}

EXPLORER_PROCESSES = {"explorer.exe"}


@dataclass(frozen=True)
class WindowSnapshot:
    process_name: str          # lower-case, e.g. "code.exe"
    exe_path: str | None
    window_title: str
    pid: int | None

    @property
    def kind(self) -> str:
        if self.process_name in BROWSER_PROCESSES:
            return "browser"
        if self.process_name in EXPLORER_PROCESSES:
            return "explorer"
        return "app"

    def identity(self) -> tuple:
        """Value used to decide whether the active window changed."""
        return (self.process_name, self.window_title)


# Cache pid -> (name, exe) to avoid repeated psutil lookups (cheap but adds up).
_proc_cache: dict[int, tuple[str, str | None]] = {}


def _process_info(pid: int) -> tuple[str, str | None]:
    if pid in _proc_cache:
        return _proc_cache[pid]
    name, exe = "unknown", None
    try:
        p = psutil.Process(pid)
        name = (p.name() or "unknown").lower()
        try:
            exe = p.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            exe = None
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        pass
    # Bound the cache size.
    if len(_proc_cache) > 512:
        _proc_cache.clear()
    _proc_cache[pid] = (name, exe)
    return name, exe


def get_active_window() -> WindowSnapshot | None:
    """Return a snapshot of the foreground window, or None if unavailable."""
    if not _HAVE_WIN32:
        return None
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None
        title = win32gui.GetWindowText(hwnd) or ""
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return None
        name, exe = _process_info(pid)
        return WindowSnapshot(
            process_name=name, exe_path=exe, window_title=title, pid=pid
        )
    except Exception as exc:  # Win32 calls can fail transiently
        log.debug("get_active_window failed: %s", exc)
        return None


def get_idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input (0.0 if unavailable)."""
    if not _HAVE_WIN32:
        return 0.0
    try:
        last_input = win32api.GetLastInputInfo()
        tick = win32api.GetTickCount()
        # GetTickCount wraps ~49.7 days; guard against negative.
        return max(0.0, (tick - last_input) / 1000.0)
    except Exception:
        return 0.0
