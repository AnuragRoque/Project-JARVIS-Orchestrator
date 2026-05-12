from __future__ import annotations

from typing import Callable
from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.core.models import ExecutionMode, PermissionDecision, RiskCategory, RiskLevel
from jarvis.modules.terminal.permissions.policy import PermissionPolicy


class PermissionManager:
    """Orchestrates permission evaluations and user modal confirmation callbacks."""

    def __init__(
        self,
        mode: ExecutionMode | None = None,
        policy: PermissionPolicy | None = None,
        confirm_callback: Callable[[str, str, RiskLevel, RiskCategory], bool] | None = None,
    ) -> None:
        self.mode = mode or settings.default_execution_mode
        self.policy = policy or PermissionPolicy()
        self.confirm_callback = confirm_callback

    def check_permission(self, command: str) -> PermissionDecision:
        decision = self.policy.evaluate(command, self.mode)
        if decision.allowed:
            return decision

        # Ask user for approval if confirmation is required and a callback is set
        if self.confirm_callback:
            approved = self.confirm_callback(
                command,
                decision.reason,
                decision.risk_level,
                decision.category,
            )
            decision.allowed = approved
            decision.user_decision = approved
        else:
            decision.allowed = False
            decision.user_decision = False

        return decision
