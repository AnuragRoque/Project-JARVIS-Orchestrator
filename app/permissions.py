"""Permission coordinator: classify any tool call, apply the mode, log it.

Reuses the terminal module's proven safety classifier + policy for PowerShell,
and maps every other tool's ``risk`` hint onto the same risk model so a single
Auto / Partial / Manual policy governs the whole tool surface.

- **Auto**    — everything runs (still classified and logged).
- **Partial** — read-only / safe actions run; risky ones ask for confirmation.
- **Manual**  — only read-only runs; everything else asks.

When confirmation is required it calls the injected ``confirm`` broker (visual +
voice); with no broker, risky actions are declined. Every decision is written to
the event log.
"""
from __future__ import annotations

import threading
from typing import Callable

from .eventlog import log_event
from .logsetup import get_logger
from jarvis.modules.terminal.core.models import (
    ExecutionMode,
    RiskCategory,
    RiskLevel,
)
from jarvis.modules.terminal.permissions.policy import PermissionPolicy
from jarvis.modules.terminal.permissions.safety import CommandSafetyClassifier

log = get_logger("permissions")

# Non-PowerShell tools declare a coarse risk hint; map it to the risk model.
_RISK_MAP: dict[str, tuple[RiskLevel, RiskCategory]] = {
    "read_only": (RiskLevel.SAFE, RiskCategory.READ_ONLY),
    "safe_action": (RiskLevel.LOW, RiskCategory.SAFE_ACTION),
    "state_change": (RiskLevel.MEDIUM, RiskCategory.SYSTEM_MODIFICATION),
    "destructive": (RiskLevel.HIGH, RiskCategory.DESTRUCTIVE),
}

# confirm(summary, reason, risk_level, category) -> bool
ConfirmFn = Callable[[str, str, RiskLevel, RiskCategory], bool]


class PermissionCoordinator:
    def __init__(self, mode: ExecutionMode = ExecutionMode.PARTIAL,
                 confirm: ConfirmFn | None = None) -> None:
        self._mode = mode
        self._confirm = confirm
        self._policy = PermissionPolicy()
        self._classifier = CommandSafetyClassifier()
        self._lock = threading.Lock()

    # ------------------------------------------------------------- mode
    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    def set_mode(self, mode) -> None:
        if isinstance(mode, str):
            mode = ExecutionMode(mode.lower())
        with self._lock:
            self._mode = mode
        log.info("Permission mode -> %s", mode.value)

    def set_confirm(self, confirm: ConfirmFn | None) -> None:
        self._confirm = confirm

    # ------------------------------------------------------------- gate
    def gate(self, name: str, args: dict, risk: str) -> tuple[bool, str]:
        """Decide whether a tool call may run. Blocks for a confirm if needed."""
        mode = self._mode
        if name == "run_powershell":
            command = (args or {}).get("command", "")
            decision = self._policy.evaluate(command, mode)
            risk_level, category, reason = (
                decision.risk_level, decision.category, decision.reason)
            auto_ok = decision.allowed
            summary = f"Run PowerShell: {command}"
            detail = command
        else:
            risk_level, category = _RISK_MAP.get(
                risk, (RiskLevel.LOW, RiskCategory.UNKNOWN))
            reason = f"{name.replace('_', ' ')} — {risk}"
            auto_ok = self._mode_allows(mode, risk_level, category)
            summary = _summarise(name, args)
            detail = _detail(args)

        if auto_ok:
            self._log(name, summary, risk_level, reason, "allowed", detail)
            return True, reason

        # Needs confirmation (Partial/Manual for a risky action).
        if self._confirm is None:
            self._log(name, summary, risk_level, reason, "declined(no-confirm)", detail)
            return False, f"{reason} (requires confirmation)"

        approved = bool(self._confirm(summary, reason, risk_level, category))
        self._log(name, summary, risk_level, reason,
                  "allowed(confirmed)" if approved else "declined(user)", detail)
        return approved, (reason if approved else f"{reason} (declined by user)")

    # ---------------------------------------------------------- helpers
    @staticmethod
    def _mode_allows(mode: ExecutionMode, level: RiskLevel,
                     category: RiskCategory) -> bool:
        if mode == ExecutionMode.AUTO:
            return True
        if mode == ExecutionMode.MANUAL:
            return category == RiskCategory.READ_ONLY and level == RiskLevel.SAFE
        # PARTIAL
        return (category in (RiskCategory.READ_ONLY, RiskCategory.SAFE_ACTION)
                or level == RiskLevel.SAFE)

    @staticmethod
    def _log(name, summary, risk_level, reason, decision, detail) -> None:
        log_event("tool", summary, module=name, detail=detail,
                  risk=getattr(risk_level, "value", str(risk_level)),
                  decision=decision)


def _summarise(name: str, args: dict) -> str:
    if not args:
        return name.replace("_", " ")
    bits = ", ".join(f"{k}={v}" for k, v in args.items())
    return f"{name.replace('_', ' ')}: {bits}"[:200]


def _detail(args: dict) -> str:
    try:
        import json
        return json.dumps(args, ensure_ascii=False, default=str)[:500]
    except Exception:
        return str(args)[:500]
