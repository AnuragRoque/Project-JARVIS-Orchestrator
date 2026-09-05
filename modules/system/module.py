"""System module: expose environment facts + discover-once app-folder lookup.

Backed by :mod:`jarvis.app.sysfacts`. Lets the orchestrator resolve where an app
stores its data (e.g. 'where is Claude's cache') with a fast shallow scan, and
REMEMBER the answer so the next request is instant. The live env facts (username,
home, %TEMP%, …) are also injected into the system prompt every turn.
"""
from __future__ import annotations

from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, Tool
from jarvis.app.sysfacts import env_snapshot, resolve_app_dir

log = get_logger("module.system")

LOCATE_APP_DIR_SPEC = {
    "type": "function",
    "function": {
        "name": "locate_app_dir",
        "description": (
            "Find where an app stores its data/cache on this PC and remember it. "
            "Use for 'where is Claude's cache', 'find Chrome's user data folder', "
            "'how big is <app>'s cache' (locate first, then size the returned path). "
            "Does a fast shallow scan of %LOCALAPPDATA%, %APPDATA% and the home "
            "folder; the result is cached, so ask once and it's known thereafter. "
            "Never invent a path — call this instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "App name to locate, e.g. 'claude', 'chrome'."},
                "refresh": {"type": "boolean",
                            "description": "Re-scan instead of using the cached result."},
            },
            "required": ["name"],
        },
    },
}

GET_SYSTEM_INFO_SPEC = {
    "type": "function",
    "function": {
        "name": "get_system_info",
        "description": (
            "Return live facts about THIS PC: username, home folder, "
            "%LOCALAPPDATA%/%APPDATA%/%TEMP%, and the real Desktop/Downloads/"
            "Documents paths. Use whenever you need a real path — never write a "
            "placeholder like C:\\Users\\<YourUsername>\\..."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


class SystemModule(Module):
    id = "system"
    name = "System"
    version = "0.1.0"

    def start(self, ctx: AppContext) -> None:
        pass

    def tools(self) -> list[Tool]:
        return [
            Tool(GET_SYSTEM_INFO_SPEC, self.get_system_info, "read_only"),
            Tool(LOCATE_APP_DIR_SPEC, self.locate_app_dir, "read_only"),
        ]

    # ------------------------------------------------------------- handlers
    def get_system_info(self) -> dict:
        return env_snapshot()

    def locate_app_dir(self, name: str = "", refresh: bool = False) -> dict:
        return resolve_app_dir(name, refresh=bool(refresh))


def get_module() -> Module:
    return SystemModule()
