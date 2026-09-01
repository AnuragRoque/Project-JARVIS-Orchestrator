"""The orchestrator: a tool-calling ReAct loop on a worker thread.

Generalised from the terminal module's single-tool agent. It receives the full
tool set from the :class:`ToolRouter` and lets the model choose: answer directly,
or call one or more tools, feeding results back until it produces a final reply.

Runs on its own QThread; emits signals the hub UI renders. Tool handlers that
must touch the GUI thread (e.g. the PowerShell engine) marshal internally, so the
loop can call them synchronously.
"""
from __future__ import annotations

import json
import time
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from .logsetup import get_logger
from .tool_router import ToolRouter

log = get_logger("orchestrator")

_RETRY_ATTEMPTS = 3          # transient provider/network errors are retried
_RETRY_BACKOFF = 0.7         # seconds, multiplied by the attempt number
# Substrings that mark a permanent error not worth retrying (auth/quota/bad model).
_NO_RETRY = ("invalid api key", "incorrect api key", "authentication",
             "no api key", "missing", "model_not_found", "does not exist",
             "insufficient_quota", "unsupported")

# gate(name, args, risk) -> (allowed: bool, reason: str)
PermissionGate = Callable[[str, dict, str], tuple[bool, str]]


def _allow_all(name: str, args: dict, risk: str) -> tuple[bool, str]:
    return True, "allowed"


class Orchestrator(QThread):
    status = pyqtSignal(str)
    tool_started = pyqtSignal(str, str)    # name, args summary
    tool_finished = pyqtSignal(str, str)   # name, result preview
    final = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        provider,
        model: str,
        messages: list[dict],
        router: ToolRouter,
        gate: PermissionGate | None = None,
        max_steps: int = 8,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.provider = provider
        self.model = model
        self.messages = list(messages)
        self.router = router
        self.gate = gate or _allow_all
        self.max_steps = max_steps

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        specs = self.router.specs() or None
        try:
            for _step in range(self.max_steps):
                message = self._chat(specs)
                calls = self._extract_calls(message)

                if not calls:
                    self.final.emit((message.get("content") or "").strip() or "…")
                    return

                self.messages.append(message)
                for call_id, name, args in calls:
                    self._run_call(call_id, name, args)

            self.final.emit("(I reached my step limit before finishing, sir.)")
        except Exception as exc:  # provider/network errors etc.
            log.exception("Orchestrator failed")
            self.failed.emit(str(exc))

    def _chat(self, specs):
        """Call the provider with a small retry for transient failures.

        Permanent errors (bad key/model/quota) are not retried. If every attempt
        fails, the exception propagates and ``run`` reports it — the app is fine.
        """
        last = None
        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                return self.provider.chat(self.model, self.messages, tools=specs)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if any(s in str(exc).lower() for s in _NO_RETRY):
                    raise
                log.warning("provider.chat attempt %d/%d failed: %s",
                            attempt, _RETRY_ATTEMPTS, exc)
                if attempt < _RETRY_ATTEMPTS:
                    self.status.emit(f"Reconnecting… (attempt {attempt + 1})")
                    time.sleep(_RETRY_BACKOFF * attempt)
        raise last

    def _run_call(self, call_id: str, name: str, args: dict) -> None:
        tool = self.router.get(name)
        risk = tool.risk if tool else "unknown"
        self.tool_started.emit(name, _summarise_args(name, args))

        allowed, reason = self.gate(name, args, risk)
        if not allowed:
            result = (
                f"[DECLINED] {reason}. This action was not performed; tell the user "
                f"it needs confirmation or was skipped."
            )
        else:
            self.status.emit(f"Running {name}…")
            result = self.router.dispatch(name, args)

        self.tool_finished.emit(name, _preview(result))
        self.messages.append(
            {"role": "tool", "tool_call_id": call_id, "content": result})

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _extract_calls(message: dict) -> list[tuple[str, str, dict]]:
        calls: list[tuple[str, str, dict]] = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call.get("function", {}) or {}
            name = fn.get("name")
            if not name:
                continue
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            call_id = call.get("id") or f"call_{i}"
            calls.append((call_id, name, args if isinstance(args, dict) else {}))
        return calls


def _summarise_args(name: str, args: dict) -> str:
    if name == "run_powershell":
        return str(args.get("command", ""))
    if not args:
        return ""
    try:
        return json.dumps(args, ensure_ascii=False, default=str)[:160]
    except (TypeError, ValueError):
        return str(args)[:160]


def _preview(result: str, limit: int = 220) -> str:
    text = " ".join((result or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")
