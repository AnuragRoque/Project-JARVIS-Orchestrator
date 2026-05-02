from __future__ import annotations

import base64
import os
import shutil
import uuid
from typing import Callable

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.core.logging import logger
from jarvis.modules.terminal.core.models import CommandResult


def _find_powershell_executable() -> str:
    """Find the full absolute path to powershell.exe or pwsh.exe."""
    system32_ps = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    if os.path.exists(system32_ps):
        return system32_ps
    found = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if found:
        return found
    return "powershell.exe"


class PowerShellEngine(QObject):
    """Persistent PowerShell process manager running over stdin/stdout pipes."""

    output_received = pyqtSignal(str)
    session_started = pyqtSignal()
    session_ended = pyqtSignal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._capturing = False
        self._cap_marker = ""
        self._cap_buffer: list[str] = []
        self._cap_carry = ""
        self._cap_done: Callable[[CommandResult], None] | None = None

        self._cap_timer = QTimer(self)
        self._cap_timer.setSingleShot(True)
        self._cap_timer.timeout.connect(self._on_capture_timeout)

        self.start_session()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() == QProcess.ProcessState.Running

    def start_session(self) -> bool:
        """(Re)start the persistent PowerShell session synchronously."""
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)

        self._capturing = False
        self._cap_carry = ""
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.finished.connect(self._on_finished)

        start_dir = os.path.join(os.path.expanduser("~"), "Documents")
        if os.path.isdir(start_dir):
            self._process.setWorkingDirectory(start_dir)

        ps_path = _find_powershell_executable()
        init = "[Console]::OutputEncoding=[Text.Encoding]::UTF8"
        self._process.start(
            ps_path,
            ["-NoLogo", "-NoProfile", "-NoExit", "-Command", init],
        )

        started = self._process.waitForStarted(3000)
        if started:
            logger.info(f"PowerShell session started successfully using {ps_path}")
            self.session_started.emit()
            return True
        else:
            logger.error(f"Failed to start PowerShell process using {ps_path}")
            self._append_raw("\n[terminal] Failed to start powershell.exe\n")
            return False

    def send_interactive(self, command: str) -> None:
        """Send a manual interactive command from the UI terminal input bar."""
        if not self.is_running:
            if not self.start_session():
                return
        if self._process and self.is_running:
            self._process.write((command + "\r\n").encode("utf-8"))

    def run_captured(
        self,
        command: str,
        on_done: Callable[[CommandResult], None],
        timeout_ms: int | None = None,
    ) -> None:
        """Run command in the persistent shell and return clean CommandResult to callback."""
        if not self.is_running:
            if not self.start_session():
                on_done(CommandResult(
                    success=False,
                    stdout="",
                    stderr="[terminal] PowerShell process is not running.",
                    timed_out=False
                ))
                return

        if timeout_ms is None:
            timeout_ms = settings.command_timeout * 1000

        self._cap_marker = "JARVIS_DONE_" + uuid.uuid4().hex
        self._cap_buffer = []
        self._cap_carry = ""
        self._cap_done = on_done
        self._capturing = True

        self._append_raw(command.strip() + "\n")

        encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
        wrapper = (
            f"$__j=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')); "
            f"try {{ Invoke-Expression $__j }} catch {{ Write-Output $_.Exception.Message }} ; "
            f"Write-Output '{self._cap_marker}'"
        )
        self._cap_timer.start(timeout_ms)
        if self._process and self.is_running:
            self._process.write((wrapper + "\r\n").encode("utf-8"))
        else:
            self._finish_capture(timed_out=False, error_msg="[terminal] Failed writing command to process")

    def _process_capture(self, text: str) -> None:
        data = self._cap_carry + text
        parts = data.split("\n")
        self._cap_carry = parts.pop()
        for idx, line in enumerate(parts):
            if line.strip() == self._cap_marker:
                self._finish_capture(timed_out=False)
                leftover = "\n".join(parts[idx + 1:])
                if self._cap_carry:
                    leftover = (leftover + "\n" if parts[idx + 1:] else "") + self._cap_carry
                    self._cap_carry = ""
                if leftover:
                    self._append_raw(leftover)
                return
            if self._cap_marker in line:
                continue
            self._append_raw(line + "\n")
            self._cap_buffer.append(line)

    def _finish_capture(self, timed_out: bool = False, error_msg: str = "") -> None:
        self._cap_timer.stop()
        self._capturing = False
        output = "\n".join(self._cap_buffer).strip()

        stderr_str = ""
        if timed_out:
            stderr_str = "[command timed out]"
        elif error_msg:
            stderr_str = error_msg

        result = CommandResult(
            success=not timed_out and not bool(error_msg),
            stdout=output,
            stderr=stderr_str,
            timed_out=timed_out,
        )

        callback = self._cap_done
        self._cap_done = None
        if callback:
            callback(result)

    def _on_capture_timeout(self) -> None:
        if not self._capturing:
            return
        self._append_raw("\n[terminal] Command timed out after limit.\n")
        self._finish_capture(timed_out=True)

    def _on_output(self) -> None:
        if not self._process:
            return
        raw = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        if self._capturing:
            self._process_capture(raw)
        else:
            self._append_raw(raw)

    def _on_finished(self, exit_code: int, _status) -> None:
        if self._capturing:
            self._finish_capture(timed_out=False, error_msg=f"[terminal] Session ended (exit code {exit_code})")
        self._append_raw(f"\n[terminal] Session ended (exit code {exit_code}).\n")
        self.session_ended.emit(exit_code)

    def _append_raw(self, text: str) -> None:
        self.output_received.emit(text)

    def shutdown(self) -> None:
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(1000)
