"""Media module: control playback + volume by sending the OS media keys.

Deterministic and reliable (no LLM-generated code needed for these common cases).
Works with whatever is playing — Spotify, YouTube in a browser, the system mixer.
"""
from __future__ import annotations

import ctypes

from jarvis.app.eventlog import log_event
from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, Tool

log = get_logger("module.media")

_KEYEVENTF_KEYUP = 0x0002
# Virtual-key codes for the multimedia keys.
_VK = {
    "playpause": 0xB3,   # VK_MEDIA_PLAY_PAUSE
    "play": 0xB3,
    "pause": 0xB3,
    "next": 0xB0,        # VK_MEDIA_NEXT_TRACK
    "previous": 0xB1,    # VK_MEDIA_PREV_TRACK
    "prev": 0xB1,
    "stop": 0xB2,        # VK_MEDIA_STOP
    "volume_up": 0xAF,   # VK_VOLUME_UP
    "volume_down": 0xAE, # VK_VOLUME_DOWN
    "mute": 0xAD,        # VK_VOLUME_MUTE
}
_ACTIONS = ["playpause", "play", "pause", "next", "previous", "stop",
            "volume_up", "volume_down", "mute"]

MEDIA_CONTROL_SPEC = {
    "type": "function",
    "function": {
        "name": "media_control",
        "description": (
            "Control media playback and volume by sending the keyboard's media "
            "keys — works with Spotify, YouTube, any player. Use for 'play', "
            "'pause', 'next song', 'previous', 'turn the volume up/down', 'mute'. "
            "For volume, 'steps' sets how many notches (each ≈2%)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": _ACTIONS,
                           "description": "The media/volume action."},
                "steps": {"type": "integer",
                          "description": "For volume_up/volume_down: number of notches (default 5)."},
            },
            "required": ["action"],
        },
    },
}


class MediaModule(Module):
    id = "media"
    name = "Media"
    version = "0.1.0"

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def tools(self) -> list[Tool]:
        return [Tool(MEDIA_CONTROL_SPEC, self.media_control, "safe_action")]

    # ------------------------------------------------------------- handler
    def media_control(self, action: str = "", steps: int = 5) -> dict:
        action = (action or "").strip().lower().replace(" ", "_")
        vk = _VK.get(action)
        if vk is None:
            return {"ok": False,
                    "error": f"Unknown media action '{action}'. Options: {', '.join(_ACTIONS)}."}
        presses = max(1, int(steps or 1)) if action in ("volume_up", "volume_down") else 1
        try:
            for _ in range(presses):
                _tap(vk)
        except Exception as exc:
            log.exception("media_control failed")
            return {"ok": False, "error": f"Media key failed: {exc}"}
        log_event("media", f"{action} x{presses}", module="media", decision="sent")
        return {"ok": True, "action": action, "presses": presses,
                "message": f"Done — {action.replace('_', ' ')}."}


def _tap(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


def get_module() -> Module:
    return MediaModule()
