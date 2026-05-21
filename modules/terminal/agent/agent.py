from __future__ import annotations

import json
import re
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.core.logging import logger
from jarvis.modules.terminal.core.models import CommandResult
from jarvis.modules.terminal.memory.command_memory import CommandMemory
from jarvis.modules.terminal.permissions.manager import PermissionManager
from jarvis.modules.terminal.providers.base import AIProvider, ProviderError
from jarvis.modules.terminal.providers.ollama_provider import parse_text_tool_call, strip_tool_call_noise
from jarvis.modules.terminal.tools.registry import POWERSHELL_TOOL


def infer_action_command(prompt: str) -> str | None:
    """Fallback intent parser for common system actions if model outputs text without tool calls."""
    if not prompt:
        return None
    p = prompt.strip().lower()

    if any(k in p for k in ("open setting", "open settings", "win+i", "win + i", "simulate win")):
        return 'Start-Process "ms-settings:"'
    if "youtube" in p and any(k in p for k in ("open", "go", "launch", "play", "show")):
        return 'Start-Process "https://www.youtube.com"'
    if ("open edge" in p or "edge browser" in p) and "firefox" not in p:
        return 'Start-Process "msedge"'
    if "open firefox" in p:
        return 'Start-Process "firefox"'
    if "open chrome" in p:
        return 'Start-Process "chrome"'
    if "open notepad" in p:
        return 'Start-Process "notepad"'
    if "open calc" in p or "open calculator" in p:
        return 'Start-Process "calc"'
    if any(k in p for k in ("lock pc", "lock computer", "lock workstation")):
        return 'rundll32.exe user32.dll,LockWorkStation'

    return None


class Agent(QThread):
    """Autonomous ReAct tool loop running off the UI thread."""

    status = pyqtSignal(str)
    request_command = pyqtSignal(str)       # signal to UI main thread to execute command
    ran_command = pyqtSignal(str)           # signal that a command has started
    command_result = pyqtSignal(str, str)   # (command, clean_output)
    final = pyqtSignal(str)
    failed = pyqtSignal(str)
    stopped = pyqtSignal()

    MAX_GIVEUP_RETRIES = 3
    MAX_TOOL_OUTPUT = 4000

    def __init__(
        self,
        provider: AIProvider,
        model: str,
        messages: list[dict],
        permission_manager: PermissionManager | None = None,
        memory: CommandMemory | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.provider = provider
        self.model = model
        self.messages = list(messages)
        self.permission_manager = permission_manager or PermissionManager()
        self.memory = memory or CommandMemory()

        self._event = threading.Event()
        self._cmd_result = CommandResult(success=False, stdout="", stderr="")
        self._stop = False
        self._last_output = ""
        self._giveup_retries = 0
        self._history_commands: list[str] = []

    def provide_result(self, result: CommandResult | str) -> None:
        """Called by the main thread once the requested command completes."""
        if isinstance(result, str):
            self._cmd_result = CommandResult(success=not result.startswith("[terminal]"), stdout=result)
        else:
            self._cmd_result = result
        self._event.set()

    def stop(self) -> None:
        """Request cooperative cancellation."""
        self._stop = True
        self._cmd_result = CommandResult(success=False, stdout="", stderr="[stopped by user]")
        self._event.set()

    def _run_one(self, command: str) -> str:
        if self._stop:
            return "[stopped by user]"

        if self._history_commands.count(command) >= 2:
            logger.warning(f"Loop detected for command: {command}")
            return f"[LOOP_DETECTED] The command '{command}' has already been attempted repeatedly without progress. Stopping loop."

        self._history_commands.append(command)
        self.ran_command.emit(command)

        # Permission check
        decision = self.permission_manager.check_permission(command)
        if not decision.allowed:
            output = (
                f"[DECLINED] Permission to run command '{command}' was denied "
                f"({decision.reason}). Tell the user it was skipped."
            )
            self._last_output = output
            self.command_result.emit(command, output)
            return output

        self.status.emit(f"Running: {command}")
        self._event.clear()
        self.request_command.emit(command)
        self._event.wait()

        if self._stop:
            return "[stopped by user]"

        result = self._cmd_result
        if not result.success or (result.stderr and "[terminal]" in result.stderr):
            output = f"[ERROR] Command execution failed: {result.stderr or result.stdout or 'Terminal unavailable'}. Inform the user that the command failed to execute."
            self._last_output = output
            self.command_result.emit(command, output)
            return output

        output = result.stdout or "(no output)"
        if len(output) > self.MAX_TOOL_OUTPUT:
            output = output[: self.MAX_TOOL_OUTPUT] + "\n...[output truncated]"

        # Save successful execution to memory
        user_prompt = next((m.get("content", "") for m in reversed(self.messages) if m.get("role") == "user"), "")
        if user_prompt:
            self.memory.save_command(
                prompt=user_prompt,
                command=command,
                success=True,
            )

        self._last_output = output
        self.command_result.emit(command, output)
        return output + self._recovery_hint(output)

    @staticmethod
    def _recovery_hint(output: str) -> str:
        low = (output or "").lower()
        if any(sig in low for sig in ("itemnotfoundexception", "cannot find path", "does not exist")):
            return "\n(Hint: Path not found. List parent directory contents with Get-ChildItem to locate exact folder name.)"
        if "is not recognized" in low or "commandnotfoundexception" in low:
            return "\n(Hint: Command not recognized. Use a standard PowerShell cmdlet.)"
        return ""

    def run(self) -> None:
        try:
            max_steps = settings.max_agent_steps
            tools_arg = [POWERSHELL_TOOL] if self.provider.supports_tools(self.model) else None

            for step in range(max_steps):
                if self._stop:
                    self.stopped.emit()
                    return

                try:
                    message = self.provider.chat(self.model, self.messages, tools=tools_arg)
                except ProviderError as exc:
                    self.failed.emit(str(exc))
                    return

                commands = self._commands_from(message)

                # Intent fallback: If model produced text without tool calls, check for clear action intent
                if not commands and step == 0:
                    user_prompt = next((m.get("content", "") for m in reversed(self.messages) if m.get("role") == "user"), "")
                    inferred = infer_action_command(user_prompt)
                    if inferred:
                        logger.info(f"Inferred action command from user intent: '{inferred}'")
                        commands = [inferred]

                if not commands:
                    content = message.get("content", "")
                    if self._recovery_hint(self._last_output) and self._giveup_retries < self.MAX_GIVEUP_RETRIES:
                        self._giveup_retries += 1
                        self.status.emit("Retrying with alternate approach...")
                        self.messages.append(message)
                        self.messages.append({"role": "user", "content": "That path/command failed. Try listing parent folder with Get-ChildItem."})
                        continue
                    self.final.emit(strip_tool_call_noise(content))
                    return

                self.messages.append(message)
                for command in commands:
                    output = self._run_one(command)
                    if self._stop:
                        self.stopped.emit()
                        return
                    if "[LOOP_DETECTED]" in output:
                        self.final.emit(f"Stopped execution loop: {output}")
                        return
                    self.messages.append({"role": "tool", "tool_name": "run_powershell", "content": output})

            self.final.emit("(Reached maximum execution steps limit)")
        except Exception as exc:
            logger.exception("Unexpected error in Agent execution loop")
            self.failed.emit(f"Unexpected agent failure: {exc}")

    @staticmethod
    def _commands_from(message: dict) -> list[str]:
        commands: list[str] = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {}) or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            command = (args or {}).get("command") or (args or {}).get("cmd")
            if command:
                commands.append(command)
        if not commands:
            text_command = parse_text_tool_call(message.get("content", ""))
            if text_command:
                commands.append(text_command)
        return commands
