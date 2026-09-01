"""Locate files on the real filesystem by name / type, newest first.

Unlike the timeline recall (which searches *activity history*), this walks the
actual common folders — Downloads, Documents, Desktop (incl. their OneDrive
redirects) — so "the latest resume in Downloads" works even if the file was never
opened before.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

_HOME = Path(os.path.expanduser("~"))

# Windows KNOWNFOLDERID GUIDs — the authoritative paths (handle OneDrive redirects).
_FOLDERID = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
}
# Fallbacks if the shell lookup is unavailable.
_FALLBACK = {
    "downloads": ["Downloads", "OneDrive/Downloads"],
    "documents": ["Documents", "OneDrive/Documents"],
    "desktop": ["Desktop", "OneDrive/Desktop"],
    "pictures": ["Pictures", "OneDrive/Pictures"],
}
_DEFAULT_ROOTS = ("downloads", "documents", "desktop")
_SKIP_DIRS = {"node_modules", ".git", "__pycache__", "AppData", ".venv", "venv"}
_MAX_WALK = 8000  # cap files scanned so a huge tree can't hang the call


def _known_folder(name: str) -> Path | None:
    """Resolve a named folder via SHGetKnownFolderPath (OneDrive-redirect safe)."""
    guid = _FOLDERID.get(name)
    if not guid:
        return None
    try:
        import ctypes
        import uuid
        from ctypes import byref, c_wchar_p, wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        g = _GUID()
        ctypes.memmove(byref(g), uuid.UUID(guid).bytes_le, 16)
        out = c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(byref(g), 0, 0, byref(out)) == 0:
            path = out.value
            ctypes.windll.ole32.CoTaskMemFree(out)
            if path and os.path.isdir(path):
                return Path(path)
    except Exception:
        pass
    return None


def resolve_roots(folder: str | None) -> list[Path]:
    """Turn a folder hint ('downloads', a path, or None) into existing roots."""
    if folder:
        key = folder.strip().lower()
        if key in _FOLDERID:
            return _folder_paths(key)
        p = Path(os.path.expanduser(folder))
        return [p] if p.exists() else []
    roots: list[Path] = []
    for name in _DEFAULT_ROOTS:
        roots.extend(_folder_paths(name))
    return roots


def _folder_paths(name: str) -> list[Path]:
    """The canonical path for a named folder.

    Prefer the known-folder API (the ONE real location, redirect-aware). Only fall
    back to guessed paths if that lookup fails — otherwise we'd scan both
    ``~/Downloads`` and ``~/OneDrive/Downloads`` and return every file twice.
    """
    kf = _known_folder(name)
    if kf is not None:
        return [kf]
    out: list[Path] = []
    for rel in _FALLBACK.get(name, []):
        p = _HOME / rel
        if p.exists() and p not in out:
            out.append(p)
    return out


def find_files(query: str = "", folder: str | None = None,
               ext: str | None = None, limit: int = 15) -> list[dict]:
    """Return matching files (newest first) as dicts with path/name/size/modified."""
    roots = resolve_roots(folder)
    terms = [t for t in (query or "").lower().split() if t]
    exts = _norm_exts(ext)

    scanned = 0
    hits: list[dict] = []
    seen: set[str] = set()
    scanned_roots: set[str] = set()
    for root in roots:
        rk = os.path.normcase(os.path.abspath(root))
        if rk in scanned_roots:
            continue
        scanned_roots.add(rk)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS
                           and not d.startswith(".")]
            for fn in filenames:
                scanned += 1
                if scanned > _MAX_WALK:
                    break
                low = fn.lower()
                if exts and os.path.splitext(low)[1] not in exts:
                    continue
                if terms and not all(t in low for t in terms):
                    continue
                full = os.path.join(dirpath, fn)
                key = os.path.normcase(full)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                hits.append({
                    "path": full,
                    "name": fn,
                    "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime),
                })
            if scanned > _MAX_WALK:
                break
    hits.sort(key=lambda h: h["modified"], reverse=True)
    return hits[:max(1, int(limit or 15))]


def _norm_exts(ext: str | None) -> set[str]:
    if not ext:
        return set()
    out = set()
    for e in str(ext).replace(",", " ").split():
        e = e.strip().lower()
        if e and not e.startswith("."):
            e = "." + e
        if e:
            out.add(e)
    return out
