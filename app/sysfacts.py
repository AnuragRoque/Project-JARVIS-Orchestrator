"""System facts: what JARVIS knows about THIS machine, so it never guesses.

Two layers:

* **Live snapshot** — username, home, %LOCALAPPDATA%/%APPDATA%/%TEMP%, and the
  real Desktop/Downloads/Documents paths (OneDrive-redirect aware). These come
  straight from the environment every call, so they're always correct — no more
  ``C:\\Users\\<YourUsername>\\...`` placeholders.

* **Discover-once cache** (``system_facts`` table in jarvis.db) — app-specific
  locations (e.g. Claude's cache dir, Chrome's user-data dir) are expensive to
  hunt for, so we find them once via a cheap shallow scan and remember them.

A compact text block from :func:`prompt_block` is injected into the system
prompt each turn, and :func:`resolve_app_dir` is exposed as a tool so the model
can discover + cache a new app's folder on demand.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from .data.db import get_database
from .logsetup import get_logger

log = get_logger("sysfacts")

_lock = threading.Lock()


# --------------------------------------------------------------- live snapshot
def _known_folder(name: str) -> str:
    """Real path of a shell folder (OneDrive-aware), or '' if unavailable."""
    try:
        from jarvis.modules.documents.finder import resolve_roots
        roots = resolve_roots(name)
        return str(roots[0]) if roots else ""
    except Exception:
        return ""


def env_snapshot() -> dict[str, str]:
    """Live, always-correct environment facts (no DB, no scanning)."""
    home = os.path.expanduser("~")
    snap = {
        "username": os.environ.get("USERNAME") or os.path.basename(home),
        "home": home,
        "localappdata": os.environ.get("LOCALAPPDATA", ""),
        "appdata": os.environ.get("APPDATA", ""),
        "temp": os.environ.get("TEMP") or os.environ.get("TMP", ""),
        "computername": os.environ.get("COMPUTERNAME", ""),
        "desktop": _known_folder("desktop"),
        "downloads": _known_folder("downloads"),
        "documents": _known_folder("documents"),
    }
    return {k: v for k, v in snap.items() if v}


# --------------------------------------------------------------- fact cache
def _ensure(cur) -> None:
    cur.execute(
        "CREATE TABLE IF NOT EXISTS system_facts ("
        "key TEXT PRIMARY KEY, value TEXT, source TEXT, ts TEXT)")


def get_fact(key: str) -> str | None:
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            row = cur.execute(
                "SELECT value FROM system_facts WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
    except Exception:
        log.debug("get_fact failed", exc_info=True)
        return None


def set_fact(key: str, value: str, source: str = "discovered") -> None:
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            cur.execute(
                "INSERT INTO system_facts (key, value, source, ts) VALUES (?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "source=excluded.source, ts=excluded.ts",
                (key, value, source, datetime.now().isoformat(timespec="seconds")))
    except Exception:
        log.debug("set_fact failed", exc_info=True)


def all_facts() -> dict[str, str]:
    try:
        db = get_database()
        with db.cursor() as cur:
            _ensure(cur)
            rows = cur.execute("SELECT key, value FROM system_facts").fetchall()
            return {r["key"]: r["value"] for r in rows}
    except Exception:
        return {}


# --------------------------------------------------------- app-dir discovery
def _dir_size(path: str, max_files: int = 200_000) -> tuple[int, bool]:
    """Total bytes under ``path`` (capped so a huge tree can't hang). Returns
    (bytes, capped)."""
    total = 0
    count = 0
    for dirpath, _dirs, files in os.walk(path):
        for fn in files:
            count += 1
            if count > max_files:
                return total, True
            try:
                total += os.stat(os.path.join(dirpath, fn)).st_size
            except OSError:
                continue
    return total, False


def _human_size(n: float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def resolve_app_dir(name: str, refresh: bool = False,
                    with_size: bool = False) -> dict:
    """Find (and cache) directories belonging to an app, by a cheap shallow scan.

    Scans %LOCALAPPDATA%, %APPDATA%, %USERPROFILE% ONE level deep for folders
    whose name contains ``name`` — fast and timeout-proof, unlike a deep recurse.
    Results are cached in ``system_facts`` under ``app_dir:<name>``.

    ``with_size=True`` also measures each folder's total size, so a 'how big is
    X's cache' question is answered in ONE call with no follow-up commands.
    """
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "Give an app name to locate."}
    key = f"app_dir:{name.lower()}"
    dirs: list[str] | None = None
    cached_hit = False
    if not refresh:
        cached = get_fact(key)
        if cached is not None:
            try:
                dirs = json.loads(cached)
            except (TypeError, ValueError):
                dirs = [cached] if cached else []
            cached_hit = True

    if dirs is None:
        needle = name.lower()
        roots = [os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA"),
                 os.path.expanduser("~")]
        dirs = []
        with _lock:
            for root in roots:
                if not root or not os.path.isdir(root):
                    continue
                try:
                    for entry in os.scandir(root):
                        if entry.is_dir() and needle in entry.name.lower():
                            if entry.path not in dirs:
                                dirs.append(entry.path)
                except OSError:
                    continue
        set_fact(key, json.dumps(dirs), source="scan")

    out = {"ok": True, "app": name, "dirs": dirs, "cached": cached_hit}
    if not dirs:
        out["note"] = f"No folder matching '{name}' in the standard roots."
        return out
    if with_size:
        sized = []
        grand = 0
        for d in dirs:
            b, capped = _dir_size(d)
            grand += b
            sized.append({"path": d, "size": _human_size(b),
                          "bytes": b, **({"capped": True} if capped else {})})
        out["folders"] = sized
        out["total_size"] = _human_size(grand)
    return out


# --------------------------------------------------------- prompt block
def prompt_block() -> str:
    """Compact 'you already know this' block for the system prompt."""
    snap = env_snapshot()
    lines = ["SYSTEM FACTS (live - these are correct for THIS PC; use them, never "
             "write a placeholder like <YourUsername>):"]
    label = {
        "username": "user", "home": "home", "localappdata": "%LOCALAPPDATA%",
        "appdata": "%APPDATA%", "temp": "%TEMP%", "desktop": "Desktop",
        "downloads": "Downloads", "documents": "Documents",
        "computername": "PC name",
    }
    for k, lab in label.items():
        if snap.get(k):
            lines.append(f"- {lab}: {snap[k]}")
    cached = {k[len("app_dir:"):]: v for k, v in all_facts().items()
              if k.startswith("app_dir:")}
    if cached:
        lines.append("Known app folders (already discovered - reuse, don't re-hunt):")
        for app, val in cached.items():
            try:
                dirs = json.loads(val)
            except (TypeError, ValueError):
                dirs = [val]
            if dirs:
                lines.append(f"- {app}: {', '.join(dirs[:3])}")
    return "\n".join(lines)
