"""Typing module: 'type this …' → JARVIS types it into your last-used window.

Exposes ``type_text``. Because talking to JARVIS can leave its own window focused,
the tool first restores focus to the top-most non-JARVIS window, waits a beat, then
types via the Unicode SendInput path. Classified ``safe_action`` so it runs in
Partial/Auto without a prompt (asks only in Manual).
"""
from __future__ import annotations

import time

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, SettingField, Tool
from .keyboard import (
    focus_window,
    foreground_other_window,
    paste_text,
    type_unicode,
)
from .keyboard import press_enter as press_enter_key

log = get_logger("module.typing")

TYPE_TEXT_SPEC = {
    "type": "function",
    "function": {
        "name": "type_text",
        "description": (
            "Type text into the window the user is working in (as if typed on the "
            "keyboard). Use when the user says 'type this …', 'write … here', "
            "'fill in …'. It focuses their previous (non-JARVIS) window first. Use "
            "press_enter=true to submit/newline at the end."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The exact text to type."},
                "press_enter": {"type": "boolean",
                                "description": "Press Enter after typing (default false)."},
            },
            "required": ["text"],
        },
    },
}


class TypingModule(Module):
    id = "typing"
    name = "Typing"
    version = "0.1.0"

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def tools(self) -> list[Tool]:
        return [Tool(TYPE_TEXT_SPEC, self.type_text, "safe_action")]

    def settings_schema(self) -> list[SettingField]:
        return [
            SettingField("focus_delay_ms", "Pause before typing (ms)", "int", 450),
            SettingField("restore_focus", "Type into the previous window", "bool", True),
            SettingField("use_paste", "Type via paste (reliable) instead of keystrokes",
                         "bool", True),
        ]

    # ------------------------------------------------------------- handler
    def type_text(self, text: str = "", press_enter: bool = False) -> dict:
        if not text:
            return {"ok": False, "error": "There's no text to type."}

        cfg = self.ctx.settings if getattr(self, "ctx", None) else None
        delay_ms = int(cfg.get("focus_delay_ms", 450)) if cfg else 450
        restore = bool(cfg.get("restore_focus", True)) if cfg else True
        use_paste = bool(cfg.get("use_paste", True)) if cfg else True

        target = None
        if restore:
            try:
                hwnd = foreground_other_window()
                if hwnd:
                    focus_window(hwnd)
                    target = hwnd
            except Exception:
                log.debug("focus restore failed", exc_info=True)

        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)  # let focus settle / user click a field

        try:
            method = "paste"
            if use_paste and paste_text(text):
                if press_enter:
                    press_enter_key()
            else:  # fallback: throttled per-char keystrokes
                method = "keys"
                type_unicode(text + ("\n" if press_enter else ""))
        except Exception as exc:
            log.exception("type_text failed")
            return {"ok": False, "error": f"Typing failed: {exc}"}

        log_event("typing", f"typed {len(text)} chars ({method})", module="typing",
                  detail=text[:200], decision="typed")
        return {"ok": True, "typed_chars": len(text), "method": method,
                "focused_previous": bool(target),
                "message": f"Typed {len(text)} characters."}


def get_module() -> Module:
    return TypingModule()
