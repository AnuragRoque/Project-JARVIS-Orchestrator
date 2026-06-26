"""Reopen a previously-used resource.

Given a unified result dict from search/recall, attempt to reopen it:
  * browser visit -> open the URL in the default browser
  * file event    -> open the file with its default application
  * session/app   -> if it's a browser session, we can't recover the URL, so
                     launch the executable; for files-in-title we try to open
                     the file; otherwise launch the exe path.

Everything uses Windows-native mechanisms (os.startfile / ShellExecute) and
fails gracefully with a clear error the UI can surface.
"""
from __future__ import annotations

import os
import subprocess
import webbrowser

from ..logging_setup import get_logger

log = get_logger("resource.opener")


class OpenError(Exception):
    pass


def open_url(url: str) -> None:
    if not url:
        raise OpenError("No URL to open")
    log.info("Opening URL: %s", url)
    webbrowser.open(url)


def open_file(path: str) -> None:
    if not path:
        raise OpenError("No file path")
    if not os.path.exists(path):
        raise OpenError(f"File no longer exists: {path}")
    log.info("Opening file: %s", path)
    try:
        os.startfile(path)  # type: ignore[attr-defined]  # Windows-only
    except AttributeError:
        # Non-Windows fallback (dev machines).
        subprocess.Popen(["xdg-open", path])


def open_executable(exe_path: str | None, process_name: str | None) -> None:
    target = exe_path
    if not target or not os.path.exists(target):
        raise OpenError(
            f"Executable path unavailable for {process_name or 'application'}"
        )
    log.info("Launching executable: %s", target)
    try:
        os.startfile(target)  # type: ignore[attr-defined]
    except AttributeError:
        subprocess.Popen([target])


def open_result(result: dict) -> str:
    """Reopen the given result. Returns a short human-readable description of
    what was done. Raises OpenError on failure."""
    kind = result.get("kind")

    if kind == "browser":
        url = result.get("url")
        open_url(url)
        return f"Opened {result.get('domain') or url}"

    if kind == "file":
        path = result.get("path")
        open_file(path)
        return f"Opened {os.path.basename(path or '')}"

    if kind == "session":
        exe = result.get("exe_path")
        name = result.get("process_name")
        app = result.get("app") or name or "application"
        title_hint = result.get("window_title") or result.get("title")

        # 1) Prefer switching to an already-open window for this app.
        try:
            from .window_activation import switch_to_process
            if switch_to_process(name, title_hint):
                return f"Switched to {app}"
        except Exception:  # activation is best-effort
            log.debug("Window activation failed; will try launching")

        # 2) Otherwise launch a fresh instance of the executable.
        open_executable(exe, name)
        return f"Launched {app}"

    if kind == "resource":
        path = result.get("path")
        if path and os.path.exists(path):
            open_file(path)
            return f"Opened {os.path.basename(path)}"
        raise OpenError("Resource path unavailable")

    raise OpenError(f"Don't know how to open a '{kind}' result")
