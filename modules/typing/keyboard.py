"""Type Unicode text into the active window via the Win32 SendInput API.

Two hard parts solved here:

1. **Any character.** ``SendInput`` with ``KEYEVENTF_UNICODE`` sends real Unicode
   code points, so punctuation/emoji/accents type correctly — unlike ``SendKeys``,
   whose ``+ ^ % ~ {}`` are control characters that mangle text.
2. **The right window.** When the user talks to JARVIS, its window can hold
   keyboard focus, so keystrokes would land on JARVIS. Before typing we hand focus
   back to the top-most window that is **not** ours.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

from jarvis.app.logsetup import get_logger

log = get_logger("typing.keyboard")

# ------------------------------------------------------------- SendInput FFI
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
_VK_RETURN = 0x0D

_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", _ULONG_PTR)]


class _MOUSEINPUT(ctypes.Structure):  # only here so INPUT has the correct size
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _key_event(code: int, flags: int) -> _INPUT:
    ki = _KEYBDINPUT(wVk=0, wScan=code, dwFlags=flags, time=0, dwExtraInfo=0)
    return _INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=ki))


def _send(events: list[_INPUT]) -> int:
    n = len(events)
    arr = (_INPUT * n)(*events)
    return ctypes.windll.user32.SendInput(n, arr, ctypes.sizeof(_INPUT))


def type_unicode(text: str, per_char_delay: float = 0.006) -> int:
    """Type `text` char-by-char (fallback path). '\\n' becomes Enter.

    A small per‑char delay is REQUIRED: injecting Unicode with no gap makes fast
    apps drop key‑up events, so a key "sticks" and auto‑repeats (the 'aaaa…' /
    '))))' garbage). The primary path is :func:`paste_text`, which avoids this.
    """
    sent = 0
    for ch in text:
        if ch == "\n":
            _send([_key_event(_VK_RETURN, 0)])
            _send([_key_event(_VK_RETURN, KEYEVENTF_KEYUP)])
        else:
            code = ord(ch)
            _send([_key_event(code, KEYEVENTF_UNICODE)])
            _send([_key_event(code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)])
        sent += 1
        if per_char_delay:
            time.sleep(per_char_delay)
    return sent


# --------------------------------------------------------- clipboard paste
def _get_clipboard_text():
    import win32clipboard as clip
    for _ in range(5):
        try:
            clip.OpenClipboard()
            try:
                if clip.IsClipboardFormatAvailable(clip.CF_UNICODETEXT):
                    return clip.GetClipboardData(clip.CF_UNICODETEXT)
                return None
            finally:
                clip.CloseClipboard()
        except Exception:
            time.sleep(0.03)
    return None


def _set_clipboard_text(text: str) -> bool:
    import win32clipboard as clip
    for _ in range(5):
        try:
            clip.OpenClipboard()
            try:
                clip.EmptyClipboard()
                clip.SetClipboardData(clip.CF_UNICODETEXT, text)
                return True
            finally:
                clip.CloseClipboard()
        except Exception:
            time.sleep(0.03)
    return False


def _ctrl_v() -> None:
    u = ctypes.windll.user32
    VK_CONTROL, VK_V = 0x11, 0x56
    u.keybd_event(VK_CONTROL, 0, 0, 0)
    u.keybd_event(VK_V, 0, 0, 0)
    u.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
    u.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def press_enter() -> None:
    _send([_key_event(_VK_RETURN, 0)])
    _send([_key_event(_VK_RETURN, KEYEVENTF_KEYUP)])


def paste_text(text: str) -> bool:
    """Type by pasting: set the clipboard, send Ctrl+V, then restore the clipboard.

    Reliable for arbitrary Unicode/newlines and immune to the key‑repeat garbage
    that per‑character injection produces. Returns True if the paste was issued.
    """
    saved = _get_clipboard_text()
    if not _set_clipboard_text(text):
        return False
    time.sleep(0.05)
    _ctrl_v()
    time.sleep(0.12)
    # Restore the user's previous clipboard so we don't clobber it.
    if saved is not None:
        _set_clipboard_text(saved)
    return True


# ------------------------------------------------------------- focus handling
def foreground_other_window() -> int | None:
    """Top-most visible window that doesn't belong to this (JARVIS) process."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return None
    own = os.getpid()
    found: list[int] = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return True
            if not win32gui.GetWindowText(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid and pid != own:
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)  # enumerates in Z-order (top first)
    except Exception:
        return None
    return found[0] if found else None


def focus_window(hwnd: int) -> bool:
    """Bring `hwnd` to the foreground (handles the Win32 foreground lock)."""
    try:
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return False
    try:
        fg = win32gui.GetForegroundWindow()
        cur = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        tgt = win32process.GetWindowThreadProcessId(hwnd)[0]
        if cur and tgt and cur != tgt:
            ctypes.windll.user32.AttachThreadInput(cur, tgt, True)
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if cur and tgt and cur != tgt:
                ctypes.windll.user32.AttachThreadInput(cur, tgt, False)
        return win32gui.GetForegroundWindow() == hwnd
    except Exception:
        log.debug("focus_window failed", exc_info=True)
        return False
