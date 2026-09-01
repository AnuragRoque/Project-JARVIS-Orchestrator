"""Reminders module: set / list / cancel reminders by voice or text.

"Remind me to call the recruiter at 6pm" → parses the time, stores it, and when
it's due fires a popup + spoken alert. Exposes tools to the orchestrator and a
``reminder.due`` bus event the UI turns into a toast.
"""
from __future__ import annotations

from datetime import datetime

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, SettingField, Tool
from .parse import parse_when
from .scheduler import ReminderScheduler
from .store import ReminderStore

log = get_logger("module.reminders")

SET_REMINDER_SPEC = {
    "type": "function",
    "function": {
        "name": "set_reminder",
        "description": (
            "Set a reminder for the user. Parse the time from natural language. Use "
            "for 'remind me to …', 'set a reminder …'. When it's due, JARVIS pops up "
            "and speaks the reminder."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind the user about."},
                "when": {"type": "string", "description":
                         "When, in natural language: 'in 20 minutes', 'at 6pm', "
                         "'tomorrow at 9am', 'next monday 5pm'."},
                "recurrence": {"type": "string", "enum": ["hourly", "daily", "weekly"],
                               "description": "Optional: repeat the reminder."},
            },
            "required": ["text", "when"],
        },
    },
}

LIST_REMINDERS_SPEC = {
    "type": "function",
    "function": {
        "name": "list_reminders",
        "description": "List the user's pending (not-yet-fired) reminders.",
        "parameters": {"type": "object", "properties": {}},
    },
}

CANCEL_REMINDER_SPEC = {
    "type": "function",
    "function": {
        "name": "cancel_reminder",
        "description": "Cancel a pending reminder by its id or its 1-based index "
                       "from the most recent list_reminders.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "index": {"type": "integer"},
            },
        },
    },
}


class RemindersModule(Module):
    id = "reminders"
    name = "Reminders"
    version = "0.1.0"

    def __init__(self) -> None:
        self.ctx: AppContext | None = None
        self.store: ReminderStore | None = None
        self.scheduler: ReminderScheduler | None = None
        self._order: list[int] = []  # last-listed ids for index-based cancel

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.store = ReminderStore()
        self.scheduler = ReminderScheduler(self.store, on_due=self._fire)
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler:
            self.scheduler.stop()

    def tools(self) -> list[Tool]:
        return [
            Tool(SET_REMINDER_SPEC, self.set_reminder, "safe_action"),
            Tool(LIST_REMINDERS_SPEC, self.list_reminders, "read_only"),
            Tool(CANCEL_REMINDER_SPEC, self.cancel_reminder, "safe_action"),
        ]

    def settings_schema(self) -> list[SettingField]:
        return [
            SettingField("popup", "Show a popup when a reminder is due", "bool", True),
            SettingField("speak", "Speak reminders aloud", "bool", True),
        ]

    # ------------------------------------------------------------- handlers
    def set_reminder(self, text: str = "", when: str = "",
                     recurrence: str | None = None) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "What should I remind you about?"}
        fire_at = parse_when(when)
        if fire_at is None:
            return {"ok": False,
                    "error": f"I couldn't understand the time '{when}'."}
        rid = self.store.add(text, fire_at, recurrence=recurrence, source="user")
        log_event("reminder", f"set: {text}", module="reminders",
                  detail=fire_at.isoformat(), decision="scheduled")
        return {"ok": True, "id": rid, "text": text,
                "when": _human(fire_at),
                "recurrence": recurrence or "none"}

    def list_reminders(self) -> dict:
        rows = self.store.pending()
        self._order = [r["id"] for r in rows]
        items = [
            {"index": i, "id": r["id"], "text": r["text"],
             "when": _human(datetime.fromisoformat(r["fire_at"])),
             "recurrence": r.get("recurrence") or "none"}
            for i, r in enumerate(rows, 1)
        ]
        return {"count": len(items), "reminders": items}

    def cancel_reminder(self, id: int | None = None,
                        index: int | None = None) -> dict:
        rid = id
        if rid is None and index is not None and 1 <= int(index) <= len(self._order):
            rid = self._order[int(index) - 1]
        if rid is None:
            return {"ok": False, "error": "Which reminder? Give an id or index."}
        ok = self.store.cancel(int(rid))
        return {"ok": ok, "id": rid,
                "message": "Cancelled." if ok else "No pending reminder with that id."}

    # --------------------------------------------------------------- firing
    def _fire(self, reminder: dict) -> None:
        text = reminder.get("text", "")
        log.info("Reminder due: %s", text)
        log_event("reminder", f"due: {text}", module="reminders", decision="fired")
        cfg = self.ctx.settings if self.ctx else None
        if not cfg or cfg.get("popup", True):
            try:
                self.ctx.bus.publish("reminder.due", reminder)
            except Exception:
                log.exception("publish reminder.due failed")
        if (not cfg or cfg.get("speak", True)) and self.ctx and self.ctx.speak:
            try:
                self.ctx.speak(f"Reminder: {text}")
            except Exception:
                log.exception("speak reminder failed")


def _human(dt: datetime) -> str:
    return dt.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")


def get_module() -> Module:
    return RemindersModule()
