"""Terminal module: exposes the `run_powershell` tool over a shared engine.

The orchestrator runs on a worker thread, but the :class:`PowerShellEngine` uses
a ``QProcess`` that must be driven by the GUI thread. A small bridge marshals the
call to the GUI thread and blocks the worker until the captured result returns —
so ``run_powershell`` looks like an ordinary synchronous tool.

Because the same engine backs Tab 3 (the live Terminal), commands the agent runs
also appear there with their output.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, pyqtSignal

from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, Tool
from jarvis.modules.terminal.core.models import CommandResult
from jarvis.modules.terminal.tools.powershell import PowerShellEngine

log = get_logger("module.terminal")

RUN_POWERSHELL_SPEC = {
    "type": "function",
    "function": {
        "name": "run_powershell",
        "description": (
            "Run a PowerShell command on the user's Windows PC and return its real "
            "output. Use for ANY question about the system (installed software, "
            "versions, files, folders, processes, hardware, network, dates) or to "
            "perform an action (open an app/website/settings, lock or sleep the PC). "
            "Never guess — always run a command and answer only from its real output."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The PowerShell command to execute.",
                }
            },
            "required": ["command"],
        },
    },
}


class _PowerShellBridge(QObject):
    """Runs captured commands on the GUI thread; blocks the caller for the result."""

    _trigger = pyqtSignal(str, int)

    def __init__(self, engine: PowerShellEngine) -> None:
        super().__init__()
        self.engine = engine
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._result: CommandResult | None = None
        # Queued because emitted from the worker thread; runs on the GUI thread
        # (this object lives on the GUI thread).
        self._trigger.connect(self._on_trigger)

    def run_blocking(self, command: str, timeout_s: float = 60.0) -> CommandResult:
        with self._lock:  # one command at a time
            self._event.clear()
            self._result = None
            self._trigger.emit(command, int(timeout_s * 1000))
            if not self._event.wait(timeout_s + 5):
                return CommandResult(success=False, stdout="",
                                     stderr="[terminal] command timed out")
            return self._result or CommandResult(
                success=False, stdout="", stderr="[terminal] no result")

    def _on_trigger(self, command: str, timeout_ms: int) -> None:
        self.engine.run_captured(command, self._done, timeout_ms=timeout_ms)

    def _done(self, result: CommandResult) -> None:
        self._result = result
        self._event.set()


class TerminalModule(Module):
    id = "terminal"
    name = "Terminal"
    version = "0.1.0"

    def __init__(self, engine: PowerShellEngine | None = None) -> None:
        self._engine = engine
        self._bridge: _PowerShellBridge | None = None

    def attach_engine(self, engine: PowerShellEngine) -> None:
        """Share the GUI-thread engine (the same one Tab 3 displays)."""
        self._engine = engine
        self._bridge = _PowerShellBridge(engine)

    def start(self, ctx: AppContext) -> None:
        if self._engine is None:
            self._engine = PowerShellEngine()
        if self._bridge is None:
            self._bridge = _PowerShellBridge(self._engine)

    def tools(self) -> list[Tool]:
        return [Tool(spec=RUN_POWERSHELL_SPEC, handler=self.run_powershell,
                     risk="state_change")]

    def run_powershell(self, command: str = "") -> str:
        command = (command or "").strip()
        if not command:
            return "[error] empty command"
        if self._bridge is None:
            return "[error] terminal engine not ready"
        res = self._bridge.run_blocking(command)
        if not res.success or (res.stderr and "[terminal]" in res.stderr):
            return f"[ERROR] {res.stderr or res.stdout or 'command failed'}"
        return res.stdout or "(no output)"

    def stop(self) -> None:
        # The engine is owned/torn down by the UI (Tab 3) or the runner.
        pass


def get_module() -> Module:
    return TerminalModule()
