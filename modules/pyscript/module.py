"""Python-script agent: run_python — the LLM writes Python, JARVIS runs it.

The escape hatch for "a lot of things are hard via terminal but easy in Python".
The model fills in a complete script (it may use installed libraries such as
pyautogui, pynput, pygame, psutil, PIL, requests, ctypes) and this runs it in an
isolated subprocess. State-changing ⇒ gated by permissions (confirmed in
Partial/Manual, runs in Auto). Prefer the specific tools (media_control, type_text,
power_control, find_files…) when one fits; use this for everything else.
"""
from __future__ import annotations

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, SettingField, Tool
from .runner import run_python

log = get_logger("module.pyscript")

RUN_PYTHON_SPEC = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Run a Python script to do something that's awkward via PowerShell. "
            "Write a COMPLETE, self-contained script and PRINT the result (or a "
            "confirmation) to stdout so you can read it back. Installed libraries "
            "you may use include: pyautogui and pynput (mouse/keyboard/screen), "
            "pygame (audio/graphics), psutil, PIL (Pillow), numpy, requests. "
            "Use background=true for long-running things (a game/UI window, a "
            "watcher) — it returns immediately. Prefer the dedicated tools "
            "(media_control, type_text, power_control, find_files, read_document) "
            "when one already covers the task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The complete Python script."},
                "timeout_sec": {"type": "integer",
                                "description": "Max seconds for a foreground run (default 30)."},
                "background": {"type": "boolean",
                               "description": "Run detached with no timeout/output (default false)."},
            },
            "required": ["code"],
        },
    },
}


class PyScriptModule(Module):
    id = "pyscript"
    name = "Python Runner"
    version = "0.1.0"

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def tools(self) -> list[Tool]:
        # State-changing: arbitrary code, so it's permission-gated.
        return [Tool(RUN_PYTHON_SPEC, self.run_python, "state_change")]

    def settings_schema(self) -> list[SettingField]:
        return [SettingField("default_timeout", "Default script timeout (s)", "int", 30)]

    # ------------------------------------------------------------- handler
    def run_python(self, code: str = "", timeout_sec: int = 0,
                   background: bool = False) -> dict:
        if not (code or "").strip():
            return {"ok": False, "error": "No code provided."}
        default_to = 30
        cfg = getattr(self, "ctx", None) and self.ctx.settings
        if cfg:
            try:
                default_to = int(cfg.get("default_timeout", 30))
            except Exception:
                default_to = 30
        timeout = int(timeout_sec) if timeout_sec else default_to
        result = run_python(code, timeout_sec=timeout, background=bool(background))
        log_event("pyscript", f"run_python ({'bg' if background else timeout}s)",
                  module="pyscript", detail=code[:400],
                  decision="ok" if result.get("ok") else "failed")
        return result


def get_module() -> Module:
    return PyScriptModule()
