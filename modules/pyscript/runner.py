"""Run a Python script string in an isolated subprocess.

Isolation matters: the generated code runs in a *separate* interpreter, so a crash,
hang, or heavy loop can never take down JARVIS. Foreground runs are captured and
time-limited (killed on timeout); background runs are detached for long-lived
things (a pygame window, a watcher) and return immediately.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid

from jarvis.app.logsetup import get_logger

log = get_logger("pyscript.runner")

_NO_WINDOW = 0x08000000          # CREATE_NO_WINDOW
_DETACHED = 0x00000008           # DETACHED_PROCESS
MAX_OUTPUT = 6000


def _write_temp(code: str) -> str:
    d = os.path.join(tempfile.gettempdir(), "jarvis_pyscript")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"script_{uuid.uuid4().hex[:8]}.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    return path


def run_python(code: str, timeout_sec: int = 30, background: bool = False) -> dict:
    """Execute `code`. Returns stdout/stderr/exit (foreground) or a pid (background)."""
    if not (code or "").strip():
        return {"ok": False, "error": "No code to run."}

    path = _write_temp(code)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    cwd = os.path.expanduser("~")
    exe = sys.executable or "python"

    if background:
        try:
            proc = subprocess.Popen(
                [exe, path], cwd=cwd, env=env,
                creationflags=_NO_WINDOW | _DETACHED,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL)
        except Exception as exc:
            return {"ok": False, "error": f"Failed to launch: {exc}"}
        return {"ok": True, "background": True, "pid": proc.pid,
                "message": f"Started in the background (pid {proc.pid})."}

    try:
        proc = subprocess.run(
            [exe, path], cwd=cwd, env=env, creationflags=_NO_WINDOW,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=max(1, int(timeout_sec or 30)))
    except subprocess.TimeoutExpired:
        return {"ok": False, "timeout": True,
                "error": f"Script ran past {timeout_sec}s and was stopped. "
                         f"For long-running things, use background=true."}
    except Exception as exc:
        return {"ok": False, "error": f"Execution failed: {exc}"}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    ok = proc.returncode == 0
    result = {"ok": ok, "exit_code": proc.returncode}
    if out:
        result["stdout"] = out[:MAX_OUTPUT] + ("\n…[truncated]" if len(out) > MAX_OUTPUT else "")
    if err:
        result["stderr"] = err[:MAX_OUTPUT] + ("\n…[truncated]" if len(err) > MAX_OUTPUT else "")
    if not ok and not err:
        result["error"] = f"Exited with code {proc.returncode}."
    if not out and not err and ok:
        result["message"] = "Ran successfully (no output)."
    return result
