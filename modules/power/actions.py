"""Windows power actions — Qt-free so they are unit-testable and self-contained.

Sleep / lock / hibernate have no native delay, so a delayed request is scheduled
on a :class:`threading.Timer`. Shutdown / restart use the OS's own ``/t`` delay
(and are cancellable with ``shutdown /a``). Every immediate action returns a
short human sentence the orchestrator can speak back.
"""
from __future__ import annotations

import subprocess
import threading

from jarvis.app.logsetup import get_logger

log = get_logger("power.actions")

# Hide the transient console window subprocess would otherwise flash.
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

ACTIONS = ("sleep", "lock", "hibernate", "shutdown", "restart", "cancel")


class PowerActions:
    """Executes (and can schedule / cancel) OS power actions."""

    def __init__(self) -> None:
        self._timer: threading.Timer | None = None
        self._pending: str | None = None

    # ------------------------------------------------------------ dispatch
    def run(self, action: str, delay_seconds: int = 0) -> str:
        action = (action or "").strip().lower()
        if action not in ACTIONS:
            raise ValueError(f"Unknown power action '{action}'.")

        if action == "cancel":
            return self.cancel()

        delay = max(0, int(delay_seconds or 0))

        # Shutdown / restart have a native scheduler with a cancel window.
        if action in ("shutdown", "restart"):
            flag = "/s" if action == "shutdown" else "/r"
            self._run_cmd(["shutdown", flag, "/t", str(delay)])
            self._pending = action if delay else None
            verb = "Shutting down" if action == "shutdown" else "Restarting"
            return (f"{verb} in {delay} seconds. Say 'cancel' to stop it."
                    if delay else f"{verb} now.")

        # Sleep / lock / hibernate: schedule ourselves if a delay is asked.
        if delay:
            self._schedule(action, delay)
            return f"I'll {action} the PC in {delay} seconds, sir. Say 'cancel' to stop it."
        self._execute(action)
        return {"sleep": "Going to sleep now.",
                "lock": "Locking the PC now.",
                "hibernate": "Hibernating now."}[action]

    # --------------------------------------------------------- scheduling
    def _schedule(self, action: str, delay: int) -> None:
        self.cancel()  # only one pending action at a time
        self._pending = action
        self._timer = threading.Timer(delay, self._fire, args=(action,))
        self._timer.daemon = True
        self._timer.start()
        log.info("Scheduled %s in %ss", action, delay)

    def _fire(self, action: str) -> None:
        self._timer = None
        self._pending = None
        try:
            self._execute(action)
        except Exception:
            log.exception("Scheduled %s failed", action)

    def cancel(self) -> str:
        cancelled = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
            cancelled = True
        # Also abort any pending OS shutdown/restart (harmless if none).
        try:
            self._run_cmd(["shutdown", "/a"], check=False)
        except Exception:
            pass
        was = self._pending
        self._pending = None
        if cancelled or was:
            return f"Cancelled the pending {was or 'power action'}."
        return "There's no pending power action to cancel."

    @property
    def pending(self) -> str | None:
        return self._pending

    # ----------------------------------------------------------- execute
    def _execute(self, action: str) -> None:
        if action == "lock":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        elif action == "sleep":
            self._run_cmd(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif action == "hibernate":
            self._run_cmd(["shutdown", "/h"])
        else:
            raise ValueError(action)

    @staticmethod
    def _run_cmd(cmd: list[str], check: bool = True) -> None:
        subprocess.run(cmd, creationflags=_NO_WINDOW, check=check,
                       capture_output=True)
