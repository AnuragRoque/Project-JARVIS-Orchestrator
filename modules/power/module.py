"""Power module: exposes power awareness + power actions to the orchestrator.

- ``get_power_status`` (read-only) — battery %, charging, time left, power plan.
- ``power_control`` (state-changing) — sleep / lock / hibernate / shutdown /
  restart, with an optional delay ("sleep in 10 seconds"), plus ``cancel``.

The state-changing tool is gated by the permission coordinator like any other
risky action, so in Partial/Manual mode it asks for confirmation first.
"""
from __future__ import annotations

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, SettingField, Tool
from .actions import ACTIONS, PowerActions
from .status import get_status

log = get_logger("module.power")

GET_POWER_STATUS_SPEC = {
    "type": "function",
    "function": {
        "name": "get_power_status",
        "description": (
            "Get the PC's power state: battery percentage, whether it's charging, "
            "estimated time remaining, and the active power plan. Use for 'how much "
            "battery', 'am I charging', 'battery status'."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

POWER_CONTROL_SPEC = {
    "type": "function",
    "function": {
        "name": "power_control",
        "description": (
            "Control the PC's power: sleep, lock, hibernate, shut down or restart, "
            "now or after a delay. Use 'cancel' to abort a pending/scheduled one "
            "(e.g. the user says 'cancel the shutdown'). Examples: 'sleep the PC', "
            "'lock it', 'shut down in 10 seconds', 'restart in 2 minutes'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": list(ACTIONS),
                           "description": "The power action to perform."},
                "delay_seconds": {"type": "integer",
                                  "description": "Optional delay before acting; 0 = now."},
            },
            "required": ["action"],
        },
    },
}


class PowerModule(Module):
    id = "power"
    name = "Power"
    version = "0.1.0"

    def __init__(self) -> None:
        self.ctx: AppContext | None = None
        self.actions = PowerActions()

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def stop(self) -> None:
        # Don't fire a pending action on shutdown; drop it quietly.
        try:
            self.actions.cancel()
        except Exception:
            log.debug("power cancel on stop failed", exc_info=True)

    def tools(self) -> list[Tool]:
        return [
            Tool(GET_POWER_STATUS_SPEC, self.get_power_status, "read_only"),
            Tool(POWER_CONTROL_SPEC, self.power_control, "state_change"),
        ]

    def settings_schema(self) -> list[SettingField]:
        return [
            SettingField("confirm_actions", "Always confirm power actions", "bool", True),
        ]

    # ------------------------------------------------------------- handlers
    def get_power_status(self) -> dict:
        return get_status()

    def power_control(self, action: str = "", delay_seconds: int = 0) -> dict:
        action = (action or "").strip().lower()
        try:
            message = self.actions.run(action, delay_seconds)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # OS call failed
            log.exception("power_control failed")
            return {"ok": False, "error": f"Power action failed: {exc}"}
        log_event("power", f"{action} (delay={delay_seconds}s)", module="power",
                  decision="executed")
        return {"ok": True, "action": action, "delay_seconds": int(delay_seconds or 0),
                "message": message}


def get_module() -> Module:
    return PowerModule()
