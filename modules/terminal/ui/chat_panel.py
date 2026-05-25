from __future__ import annotations

import html as _html
import re
import threading
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis.modules.terminal.agent.agent import Agent
from jarvis.modules.terminal.agent.prompts import SYSTEM_PROMPT
from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.config.user_settings import user_settings
from jarvis.modules.terminal.core.logging import logger
from jarvis.modules.terminal.core.models import (
    CommandResult,
    ExecutionMode,
    ProviderType,
    RiskCategory,
    RiskLevel,
)
from jarvis.modules.terminal.memory.command_memory import CommandMemory
from jarvis.modules.terminal.permissions.manager import PermissionManager
from jarvis.modules.terminal.permissions.safety import CommandSafetyClassifier
from jarvis.modules.terminal.permissions.policy import PermissionPolicy
from jarvis.modules.terminal.providers.base import AIProvider, ProviderError
from jarvis.modules.terminal.providers.ollama_provider import OllamaProvider
from jarvis.modules.terminal.providers.openai_provider import OpenAIProvider
from jarvis.modules.terminal.ui.permission_dialog import PermissionDialog

if TYPE_CHECKING:
    from jarvis.modules.terminal.ui.terminal_panel import TerminalPanel


def md_to_html(text: str) -> str:
    """Convert Markdown subset to Qt-friendly HTML."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    code_blocks: list[str] = []

    def _stash_block(match: re.Match) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[^\n]*\n(.*?)```", _stash_block, text, flags=re.DOTALL)
    text = re.sub(r"```(.*?)```", _stash_block, text, flags=re.DOTALL)

    text = _html.escape(text)

    inline_code: list[str] = []

    def _stash_inline(match: re.Match) -> str:
        inline_code.append(match.group(1))
        return f"\x01IC{len(inline_code) - 1}\x01"

    text = re.sub(r"`([^`]+)`", _stash_inline, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", text)

    parts: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        bullet = re.match(r"[-*+]\s+(.*)", s)
        numbered = re.match(r"\d+\.\s+(.*)", s)
        if bullet:
            parts.append(f"• {bullet.group(1)}<br>")
        elif numbered:
            parts.append(f"{numbered.group(1)}<br>")
        elif s == "":
            parts.append("<br>")
        else:
            parts.append(line + "<br>")

    out = "".join(parts)

    for i, code in enumerate(inline_code):
        out = out.replace(
            f"\x01IC{i}\x01",
            f"<code style='background:#0c0c0c;color:#9cdcfe;padding:1px 3px;border-radius:3px;'>{_html.escape(code)}</code>",
        )
    for i, code in enumerate(code_blocks):
        escaped = _html.escape(code.rstrip("\n"))
        out = out.replace(
            f"\x00CB{i}\x00",
            f"<pre style='background:#0c0c0c;color:#d4d4d4;padding:6px 8px;border-radius:6px;white-space:pre-wrap;'>{escaped}</pre>",
        )
    return out


class ModelsWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, provider: AIProvider, parent=None) -> None:
        super().__init__(parent)
        self.provider = provider

    def run(self) -> None:
        try:
            models = self.provider.list_models()
            self.loaded.emit(models)
        except ProviderError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Failed loading models: {exc}")


class ChatPanel(QWidget):
    """Chat UI Panel supporting provider selection, permission mode, fast-path matching, and streaming."""

    # Emitted (from any thread) to request a permission dialog on the GUI thread.
    _permission_requested = pyqtSignal(str, str, object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = user_settings
        self.memory = CommandMemory()

        # Restore last-used execution mode, falling back to the app default.
        saved_mode = str(self.settings.get("mode", "Partial")).lower()
        try:
            initial_mode = ExecutionMode(saved_mode)
        except ValueError:
            initial_mode = settings.default_execution_mode
        self.permission_manager = PermissionManager(
            mode=initial_mode,
            confirm_callback=self._on_permission_confirm,
        )

        # Thread-safe hand-off for permission prompts marshalled to the GUI thread.
        self._perm_event = threading.Event()
        self._perm_result = False
        self._permission_requested.connect(self._show_permission_dialog)

        self.providers: dict[ProviderType, AIProvider] = {
            ProviderType.OLLAMA: OllamaProvider(host=settings.ollama_base_url),
            ProviderType.CHATGPT: OpenAIProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
            ),
        }
        saved_provider = str(self.settings.get("provider", "Ollama")).lower()
        self.current_provider_type = (
            ProviderType.CHATGPT if saved_provider == "chatgpt" else ProviderType.OLLAMA
        )
        self.current_provider = self.providers[self.current_provider_type]
        self.current_model = str(self.settings.get("model", ""))

        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.turns: list[dict] = []
        self._pending_steps: list[dict] = []
        self._agent: Agent | None = None
        self._terminal: TerminalPanel | None = None

        self._build_ui()
        self._add_turn({"role": "assistant", "text": "Hi! I'm **Jarvis**. Ask me anything — I can inspect and manage your PC."})
        self.render()
        self.refresh_models()

    def attach_terminal(self, terminal: TerminalPanel) -> None:
        self._terminal = terminal

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header bar
        header_row = QHBoxLayout()
        header = QLabel("  CHATBOT")
        header.setObjectName("panelHeader")
        header_row.addWidget(header)
        header_row.addStretch(1)
        self.status = QLabel("● Ready")
        self.status.setObjectName("statusLabel")
        header_row.addWidget(self.status)
        layout.addLayout(header_row)

        # Provider & Execution Mode Selection Row
        controls_top = QHBoxLayout()
        controls_top.setSpacing(8)

        # Provider Selector
        prov_label = QLabel("Provider:")
        prov_label.setObjectName("panelHeader")
        controls_top.addWidget(prov_label)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Ollama", "ChatGPT"])
        self.provider_combo.setCurrentText(
            "ChatGPT" if self.current_provider_type == ProviderType.CHATGPT else "Ollama"
        )
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        controls_top.addWidget(self.provider_combo)

        # Mode Selector
        mode_label = QLabel("Mode:")
        mode_label.setObjectName("panelHeader")
        controls_top.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Manual", "Partial", "Auto"])
        index = {"manual": 0, "partial": 1, "auto": 2}.get(self.permission_manager.mode.value, 1)
        self.mode_combo.setCurrentIndex(index)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        controls_top.addWidget(self.mode_combo)

        # Model Selection Combo
        model_label = QLabel("Model:")
        model_label.setObjectName("panelHeader")
        controls_top.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(140)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        controls_top.addWidget(self.model_combo, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("miniButton")
        refresh_btn.clicked.connect(self.refresh_models)
        controls_top.addWidget(refresh_btn)

        layout.addLayout(controls_top)

        # Checkbox Controls Row
        check_row = QHBoxLayout()
        check_row.setSpacing(12)

        self.power_check = QCheckBox("🔧 Terminal power")
        self.power_check.setChecked(bool(self.settings.get("terminal_power", True)))
        self.power_check.toggled.connect(lambda v: self.settings.set("terminal_power", bool(v)))
        check_row.addWidget(self.power_check)

        self.use_saved_check = QCheckBox("⚡ Use saved commands")
        self.use_saved_check.setChecked(bool(self.settings.get("use_saved_commands", settings.memory_enabled)))
        self.use_saved_check.toggled.connect(lambda v: self.settings.set("use_saved_commands", bool(v)))
        check_row.addWidget(self.use_saved_check)

        self.steps_check = QCheckBox("🔍 Show steps")
        self.steps_check.setChecked(bool(self.settings.get("show_steps", False)))
        self.steps_check.toggled.connect(lambda v: self.settings.set("show_steps", bool(v)))
        self.steps_check.toggled.connect(self.render)
        check_row.addWidget(self.steps_check)

        check_row.addStretch(1)
        layout.addLayout(check_row)

        # Conversation view
        self.conversation = QTextEdit()
        self.conversation.setReadOnly(True)
        self.conversation.setObjectName("chatView")
        layout.addWidget(self.conversation, stretch=1)

        # Message input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Message Jarvis…")
        self.message_input.returnPressed.connect(self._send_message)
        input_row.addWidget(self.message_input, stretch=1)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        input_row.addWidget(self.stop_btn)

        layout.addLayout(input_row)

    def _on_provider_changed(self, text: str) -> None:
        if text.lower() == "chatgpt":
            self.current_provider_type = ProviderType.CHATGPT
        else:
            self.current_provider_type = ProviderType.OLLAMA

        self.current_provider = self.providers[self.current_provider_type]
        self.settings.set("provider", text)
        self.refresh_models()

    def _on_mode_changed(self, text: str) -> None:
        mode_val = text.lower()
        self.permission_manager.mode = ExecutionMode(mode_val)
        self.settings.set("mode", text)
        logger.info(f"Execution mode switched to: {self.permission_manager.mode.value}")

    def _on_model_changed(self, text: str) -> None:
        if text:
            self.current_model = text
            self.settings.set("model", text)

    def refresh_models(self) -> None:
        self._set_status("● Loading models…", "#e0b341")
        self._models_worker = ModelsWorker(self.current_provider, self)
        self._models_worker.loaded.connect(self._on_models_loaded)
        self._models_worker.failed.connect(self._on_models_failed)
        self._models_worker.start()

    def _on_models_loaded(self, models: list) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if not models:
            self.model_combo.blockSignals(False)
            self._set_status("● No models", "#e0574b")
            return
        self.model_combo.addItems(models)
        # Restore the previously selected model for this provider if still available.
        saved_model = str(self.settings.get("model", ""))
        if saved_model and saved_model in models:
            self.model_combo.setCurrentText(saved_model)
        self.model_combo.blockSignals(False)
        self.current_model = self.model_combo.currentText()
        self._set_status("● Connected", "#5ef19a")

    def _on_models_failed(self, msg: str) -> None:
        self._set_status("● Provider Offline", "#e0574b")
        logger.warning(f"Failed loading models: {msg}")

    def _on_permission_confirm(self, command: str, reason: str, risk_level: RiskLevel, category: RiskCategory) -> bool:
        """Confirm a risky command. Safe to call from the Agent worker thread.

        Qt widgets may only be created/shown on the GUI thread, so when this is
        invoked off-thread we marshal the dialog onto the GUI thread and block
        the caller until the user responds. Doing it inline on a worker thread is
        what caused the dialog to hang ("Not Responding").
        """
        if QThread.currentThread() is self.thread():
            # Already on the GUI thread (e.g. fast-path) — show directly.
            return PermissionDialog.request_approval(command, reason, risk_level, category, self)

        self._perm_event.clear()
        # Queued connection: the slot runs on the GUI thread that owns this widget.
        self._permission_requested.emit(command, reason, risk_level, category)
        self._perm_event.wait()
        return self._perm_result

    @pyqtSlot(str, str, object, object)
    def _show_permission_dialog(self, command: str, reason: str, risk_level: RiskLevel, category: RiskCategory) -> None:
        """Runs on the GUI thread; shows the modal and releases the waiting worker."""
        try:
            self._perm_result = PermissionDialog.request_approval(command, reason, risk_level, category, self)
        finally:
            self._perm_event.set()

    def _send_message(self) -> None:
        text = self.message_input.text().strip()
        if not text or self._agent is not None:
            return

        self.messages.append({"role": "user", "content": text})
        self._add_turn({"role": "user", "text": text})
        self.message_input.clear()
        self._pending_steps = []
        self.stop_btn.setEnabled(True)
        self.render()

        # Fast-Path Check
        if self.use_saved_check.isChecked() and self._terminal is not None:
            match = self.memory.find_match(text)
            if match:
                self._run_fast_path(match.command, text, match.match_id)
                return

        self._run_agent()

    def _run_fast_path(self, command: str, user_prompt: str, match_id: int) -> None:
        self._set_status("● Fast-path executing…", "#5ef19a")
        decision = self.permission_manager.check_permission(command)
        if not decision.allowed:
            declined = f"[DECLINED] '{command}' permission denied."
            self._pending_steps = [{"cmd": command, "output": declined}]
            self._finish_assistant(f"Skipped — command permission denied:\n`{command}`")
            return

        self._pending_steps = [{"cmd": command, "output": None}]
        self.render()
        self._terminal.run_captured(
            command,
            lambda res: self._on_fast_path_done(command, res, user_prompt, match_id),
        )

    def _on_fast_path_done(self, command: str, res: CommandResult, user_prompt: str, match_id: int) -> None:
        output = res.stdout or res.stderr
        if not res.success or res.timed_out or output.startswith(("[terminal]", "[ERROR]")):
            # Fast path failed — purge bad match and fallback to agent
            self.memory.purge_command(match_id)
            self._pending_steps = []
            self._run_agent()
            return

        self._pending_steps = [{"cmd": command, "output": output}]
        summary = f"⚡ **Executed saved command:** `{command}`\n\n```\n{output}\n```" if output else f"⚡ **Executed saved command:** `{command}`"
        self.messages.append({"role": "assistant", "content": summary})
        self._finish_assistant(summary)

    def _run_agent(self) -> None:
        self._set_status("● Thinking…", "#e0b341")

        # Prune context passed to agent: System prompt + last 6 user/assistant turns
        pruned_messages = [self.messages[0]]
        recent = [m for m in self.messages[1:] if m.get("role") in ("user", "assistant")][-6:]
        pruned_messages.extend(recent)

        self._agent = Agent(
            provider=self.current_provider,
            model=self.current_model,
            messages=pruned_messages,
            permission_manager=self.permission_manager,
            memory=self.memory,
            parent=self,
        )
        self._agent.status.connect(lambda msg: self._set_status(f"● {msg}", "#e0b341"))
        self._agent.ran_command.connect(self._on_agent_ran)
        self._agent.command_result.connect(self._on_agent_result)
        self._agent.request_command.connect(self._on_agent_command)
        self._agent.final.connect(self._on_agent_final)
        self._agent.failed.connect(self._on_agent_failed)
        self._agent.stopped.connect(self._on_agent_stopped)
        self._agent.start()

    def _on_agent_ran(self, command: str) -> None:
        self._pending_steps.append({"cmd": command, "output": None})
        self.render()

    def _on_agent_result(self, command: str, output: str) -> None:
        for step in reversed(self._pending_steps):
            if step["cmd"] == command and step["output"] is None:
                step["output"] = output
                break
        else:
            self._pending_steps.append({"cmd": command, "output": output})
        self.render()

    def _on_agent_command(self, command: str) -> None:
        if self._terminal is None or self._agent is None:
            if self._agent:
                self._agent.provide_result(CommandResult(success=False, stdout="", stderr="[no terminal attached]"))
            return
        self._terminal.run_captured(command, self._agent.provide_result)

    def _on_agent_final(self, content: str) -> None:
        if self._agent:
            if content.strip():
                self.messages.append({"role": "assistant", "content": content})
        self._agent = None
        self._finish_assistant(content or "(no response)")

    def _on_agent_failed(self, error: str) -> None:
        self._agent = None
        self._finish_assistant(f"⚠️ {error}", status=("● Error", "#e0574b"))

    def _on_agent_stopped(self) -> None:
        self._agent = None
        self._finish_assistant("_Stopped by user._", status=("● Stopped", "#e0b341"))

    def _finish_assistant(self, text: str, status=("● Ready", "#5ef19a")) -> None:
        if self._pending_steps:
            self._add_turn({"role": "process", "steps": self._pending_steps})
            self._pending_steps = []
        self._add_turn({"role": "assistant", "text": text})
        self._set_status(*status)
        self.stop_btn.setEnabled(False)
        self.render()

    def _on_stop(self) -> None:
        if self._agent is not None:
            self._agent.stop()
        self.stop_btn.setEnabled(False)

    def _add_turn(self, turn: dict) -> None:
        self.turns.append(turn)

    def render(self) -> None:
        show_steps = self.steps_check.isChecked()
        turns = list(self.turns)
        if self._pending_steps:
            turns.append({"role": "process", "steps": self._pending_steps})

        parts: list[str] = []
        for turn in turns:
            role = turn["role"]
            if role == "user":
                body = _html.escape(turn["text"]).replace("\n", "<br>")
                parts.append(f"<div style='margin:8px 0;'><span style='color:#4fc3f7;font-weight:600;'>You</span><div>{body}</div></div>")
            elif role == "assistant":
                parts.append(f"<div style='margin:8px 0;'><span style='color:#81c784;font-weight:600;'>Jarvis</span><div>{md_to_html(turn['text'])}</div></div>")
            elif role == "process" and show_steps:
                parts.append(self._process_html(turn["steps"]))

        self.conversation.setHtml("".join(parts))
        bar = self.conversation.verticalScrollBar()
        bar.setValue(bar.maximum())

    @staticmethod
    def _process_html(steps: list) -> str:
        rows: list[str] = []
        for step in steps:
            cmd = _html.escape(step["cmd"])
            out = step["output"]
            blocked = isinstance(out, str) and out.startswith(("[BLOCKED]", "[DECLINED]", "[ERROR]"))
            head = "#e0574b" if blocked else "#e0b341"
            rows.append(f"<div style='margin:2px 0;'><span style='color:{head};'>❯</span> <code style='color:#9cdcfe;'>{cmd}</code></div>")
            if out is None:
                rows.append("<div style='color:#777;margin:0 0 4px 14px;'>running…</div>")
            else:
                shown = _html.escape(out if len(out) <= 800 else out[:800] + " …")
                rows.append(f"<pre style='color:#b5b5b5;background:#0c0c0c;margin:0 0 6px 14px;padding:4px 6px;border-radius:4px;white-space:pre-wrap;'>{shown}</pre>")
        return f"<div style='margin:6px 0;border-left:2px solid #333349;padding-left:8px;'><div style='color:#9aa0b5;font-size:11px;'>steps</div>{''.join(rows)}</div>"

    def _set_status(self, text: str, color: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color}; font-weight: 600;")

    def shutdown(self) -> None:
        if self._agent and self._agent.isRunning():
            self._agent.stop()
            self._agent.wait(500)
