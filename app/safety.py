"""Process-wide crash guard.

The single most important resilience piece: in PyQt an unhandled Python
exception in a slot or virtual method reaches ``sys.excepthook`` and the default
handler aborts the process (``qFatal``). We install a handler that **logs and
returns**, so a bug in one feature never takes the whole app down. Same for
background threads via ``threading.excepthook``.

``KeyboardInterrupt`` / ``SystemExit`` still pass through so the app can quit.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

from .logsetup import get_logger

log = get_logger("safety")

_notify: Callable[[str], None] | None = None
_last_notify = 0.0
_NOTIFY_GAP = 15.0  # seconds between user-facing "an error was handled" nudges


def set_error_notifier(fn: Callable[[str], None] | None) -> None:
    """Optional hook (e.g. a tray balloon) called when an error is swallowed."""
    global _notify
    _notify = fn


def _maybe_notify(exc: BaseException) -> None:
    global _last_notify
    now = time.time()
    if _notify is not None and (now - _last_notify) > _NOTIFY_GAP:
        _last_notify = now
        try:
            _notify(f"A background error was handled — JARVIS is still running "
                    f"({type(exc).__name__}).")
        except Exception:
            pass


def _handle(exc_type, exc, tb, where: str) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc, tb)  # let normal exit happen
        return
    try:
        log.error("Unhandled %s in %s: %s", exc_type.__name__, where, exc,
                  exc_info=(exc_type, exc, tb))
    except Exception:
        pass
    _maybe_notify(exc)


def install_excepthook() -> None:
    """Install the non-fatal handlers. Call once, early, on the main thread."""
    sys.excepthook = lambda t, e, tb: _handle(t, e, tb, "slot/main")

    if hasattr(threading, "excepthook"):  # Python 3.8+
        def _thread_hook(args) -> None:
            name = getattr(args.thread, "name", "?")
            _handle(args.exc_type, args.exc_value, args.exc_traceback, f"thread:{name}")
        threading.excepthook = _thread_hook

    log.info("Global exception guard installed")


def guard(fn: Callable, *, where: str = "callback"):
    """Wrap a callable so it can never raise into Qt (for timers/slots).

    Returns a wrapper that logs and swallows any exception. Use for periodic
    timer callbacks where a single bad tick shouldn't be able to abort the app.
    """
    def _wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.exception("Guarded %s failed", where)
            _maybe_notify(exc)
            return None
    return _wrapped
