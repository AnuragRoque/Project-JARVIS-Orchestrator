"""Find and focus an already-running window (Win32).

When the user reopens an *application/session* result, we'd rather switch to the
existing window than spawn a second instance. We enumerate top-level windows,
match them to the recorded process (and, when possible, the recorded title), and
bring the best match to the foreground.

Windows guards the foreground with a "foreground lock" that makes a naked
``SetForegroundWindow`` silently fail when the caller isn't the active app. We
use the well-known work-arounds: restore if minimised, briefly attach to the
foreground thread's input queue, and nudge with an ALT keypress.
"""
from __future__ import annotations

from difflib import SequenceMatcher

import psutil

from ..logging_setup import get_logger

log = get_logger("resource.activate")

try:
    import win32gui
    import win32con
    import win32process
    import win32api
    _HAVE_WIN32 = True
except ImportError:
    _HAVE_WIN32 = False


def _proc_name(pid: int) -> str:
    try:
        return (psutil.Process(pid).name() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return ""


def _enum_windows() -> list[tuple[int, int, str]]:
    """Return (hwnd, pid, title) for visible, titled top-level windows."""
    out: list[tuple[int, int, str]] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        out.append((hwnd, pid, title))

    win32gui.EnumWindows(cb, None)
    return out


def _title_score(recorded: str, candidate: str) -> float:
    if not recorded:
        return 0.0
    r, c = recorded.lower(), candidate.lower()
    if r == c:
        return 1.0
    if r in c or c in r:
        return 0.85
    return SequenceMatcher(None, r, c).ratio()


def find_window(process_name: str | None, title_hint: str | None):
    """Return the hwnd of the best-matching open window, or None."""
    if not _HAVE_WIN32 or not process_name:
        return None
    target = process_name.lower()
    candidates = []
    for hwnd, pid, title in _enum_windows():
        if _proc_name(pid) != target:
            continue
        candidates.append((hwnd, _title_score(title_hint or "", title)))
    if not candidates:
        return None
    # Best title match wins; ties fall back to the first found.
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def activate_window(hwnd) -> bool:
    """Bring hwnd to the foreground. Returns True on success."""
    if not _HAVE_WIN32 or not hwnd:
        return False
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # Attach to the current foreground thread to defeat the foreground lock.
        fg = win32gui.GetForegroundWindow()
        cur_thread = win32api.GetCurrentThreadId()
        fg_thread = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]

        attached = []
        for other in {fg_thread, target_thread}:
            if other and other != cur_thread:
                try:
                    win32process.AttachThreadInput(cur_thread, other, True)
                    attached.append(other)
                except Exception:
                    pass
        try:
            # An ALT tap makes Windows treat us as allowed to steal focus.
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0,
                                 win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
        finally:
            for other in attached:
                try:
                    win32process.AttachThreadInput(cur_thread, other, False)
                except Exception:
                    pass
        return win32gui.GetForegroundWindow() == hwnd
    except Exception as exc:
        log.debug("activate_window failed: %s", exc)
        return False


def switch_to_process(process_name: str | None, title_hint: str | None) -> bool:
    """Find and focus a window for the given process. True if switched."""
    hwnd = find_window(process_name, title_hint)
    if hwnd is None:
        return False
    return activate_window(hwnd)
