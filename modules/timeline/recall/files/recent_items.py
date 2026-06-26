"""Read the Windows "Recent Items" folder to recover recently opened files.

Windows maintains ``%APPDATA%\\Microsoft\\Windows\\Recent`` full of ``.lnk``
shortcuts pointing at recently used documents. This is a reliable, native, and
non-invasive signal (no filesystem watching required). We resolve each shortcut
to its target path and use the shortcut's modification time as the last-activity
timestamp.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..logging_setup import get_logger

log = get_logger("files.recent")

try:
    import win32com.client  # type: ignore
    _HAVE_SHELL = True
except ImportError:
    _HAVE_SHELL = False


def recent_dir() -> Path:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(appdata) / "Microsoft" / "Windows" / "Recent"


# File extensions worth remembering as "documents/resources".
MEANINGFUL_EXTS = {
    # docs
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "md", "rtf",
    "odt", "csv", "epub",
    # code / config
    "py", "js", "ts", "tsx", "jsx", "java", "c", "cpp", "h", "cs", "go", "rs",
    "rb", "php", "swift", "kt", "sql", "json", "yaml", "yml", "toml", "ini",
    "sh", "ps1", "html", "css", "xml",
    # media / design
    "png", "jpg", "jpeg", "gif", "svg", "psd", "fig", "mp4", "mp3", "wav",
    # archives / data
    "zip", "db", "sqlite", "ipynb",
}


@dataclass
class RecentFile:
    path: str
    last_activity: datetime


def _resolve_lnk(shortcut_path: Path):
    """Return (target_path, mtime) for a .lnk, or None."""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(str(shortcut_path))
        target = sc.TargetPath
        if not target:
            return None
        mtime = datetime.fromtimestamp(
            shortcut_path.stat().st_mtime, tz=timezone.utc
        ).replace(tzinfo=None)
        return target, mtime
    except Exception as exc:
        log.debug("Failed to resolve %s: %s", shortcut_path.name, exc)
        return None


def scan_recent_files(limit: int = 400) -> list[RecentFile]:
    """Return recently used *files* (not folders) from Recent Items."""
    if not _HAVE_SHELL:
        return []
    folder = recent_dir()
    if not folder.exists():
        return []

    out: list[RecentFile] = []
    try:
        entries = sorted(
            folder.glob("*.lnk"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]
    except OSError:
        return []

    for lnk in entries:
        resolved = _resolve_lnk(lnk)
        if not resolved:
            continue
        target, mtime = resolved
        # Skip directories and non-existent / non-file targets.
        if not target or target.endswith(("\\", "/")):
            continue
        ext = os.path.splitext(target)[1].lstrip(".").lower()
        if ext and ext not in MEANINGFUL_EXTS:
            continue
        # Some targets are UNC/network or removed; keep path but skip dirs.
        if os.path.isdir(target):
            continue
        out.append(RecentFile(path=target, last_activity=mtime))
    return out
