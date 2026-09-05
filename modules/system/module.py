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
            "Find where an app stores its data/cache on this PC, and (optionally) "
            "how big those folders are — in ONE call. Use for 'where is Claude's "
            "cache', 'how big is <app>'s cache'. Call it ONCE with the base app name "
            "(e.g. 'antigravity', NOT 'antigravity-updater' too) — it already matches "
            "every related folder. For a size question pass with_size=true and you "
            "will NOT need any follow-up PowerShell. Result is cached; ask once and "
            "it's known thereafter. Never invent a path — call this instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "Base app name to locate, e.g. 'claude', 'chrome'."},
                "with_size": {"type": "boolean",
                              "description": "Also measure each folder's total size (one call, no extra commands)."},
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

    def locate_app_dir(self, name: str = "", refresh: bool = False,
                       with_size: bool = False) -> dict:
        return resolve_app_dir(name, refresh=bool(refresh),
                               with_size=bool(with_size))


def get_module() -> Module:
    return SystemModule()
