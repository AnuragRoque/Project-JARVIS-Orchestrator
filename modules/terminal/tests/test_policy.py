import pytest
from jarvis.modules.terminal.core.models import ExecutionMode, RiskCategory, RiskLevel
from jarvis.modules.terminal.permissions.policy import PermissionPolicy


@pytest.fixture
def policy():
    return PermissionPolicy()


def test_manual_mode(policy):
    # Read only allowed
    decision = policy.evaluate("Get-Location", ExecutionMode.MANUAL)
    assert decision.allowed is True

    # Risky requires approval
    decision = policy.evaluate("Remove-Item test.txt", ExecutionMode.MANUAL)
    assert decision.allowed is False


def test_partial_mode(policy):
    # Read only allowed automatically
    decision = policy.evaluate("Get-Location", ExecutionMode.PARTIAL)
    assert decision.allowed is True

    # Safe app launch allowed automatically
    decision = policy.evaluate("start-process notepad", ExecutionMode.PARTIAL)
    assert decision.allowed is True

    # State modifying command requires approval
    decision = policy.evaluate("Remove-Item test.txt", ExecutionMode.PARTIAL)
    assert decision.allowed is False


def test_auto_mode(policy):
    decision = policy.evaluate("Remove-Item test.txt", ExecutionMode.AUTO)
    assert decision.allowed is True
