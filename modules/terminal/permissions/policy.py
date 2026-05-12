from __future__ import annotations

from jarvis.modules.terminal.core.models import (
    ExecutionMode,
    PermissionDecision,
    RiskCategory,
    RiskLevel,
)
from jarvis.modules.terminal.permissions.safety import CommandSafetyClassifier


class PermissionPolicy:
    """Evaluates execution modes (MANUAL, PARTIAL, AUTO) against command risk levels."""

    def __init__(self, classifier: CommandSafetyClassifier | None = None) -> None:
        self.classifier = classifier or CommandSafetyClassifier()

    def evaluate(self, command: str, mode: ExecutionMode) -> PermissionDecision:
        risk_level, category, reason = self.classifier.classify(command)

        if mode == ExecutionMode.AUTO:
            # AUTO mode permits normal execution automatically
            return PermissionDecision(
                allowed=True,
                mode=mode,
                risk_level=risk_level,
                category=category,
                reason=reason,
                command=command,
                user_decision=True,
            )

        if mode == ExecutionMode.MANUAL:
            # MANUAL mode requires confirmation for any command that is not read-only
            if category == RiskCategory.READ_ONLY and risk_level == RiskLevel.SAFE:
                return PermissionDecision(
                    allowed=True,
                    mode=mode,
                    risk_level=risk_level,
                    category=category,
                    reason=reason,
                    command=command,
                    user_decision=None,
                )
            return PermissionDecision(
                allowed=False,
                mode=mode,
                risk_level=risk_level,
                category=category,
                reason=reason,
                command=command,
                user_decision=None,
            )

        # PARTIAL mode (Recommended Default):
        # Auto-allow READ_ONLY and SAFE_ACTION operations
        if category in (RiskCategory.READ_ONLY, RiskCategory.SAFE_ACTION) or risk_level == RiskLevel.SAFE:
            return PermissionDecision(
                allowed=True,
                mode=mode,
                risk_level=risk_level,
                category=category,
                reason=reason,
                command=command,
                user_decision=None,
            )

        # Require explicit user confirmation for state modifications / risky commands
        return PermissionDecision(
            allowed=False,
            mode=mode,
            risk_level=risk_level,
            category=category,
            reason=reason,
            command=command,
            user_decision=None,
        )
