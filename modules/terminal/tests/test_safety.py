import pytest
from jarvis.modules.terminal.core.models import RiskCategory, RiskLevel
from jarvis.modules.terminal.permissions.safety import CommandSafetyClassifier


@pytest.fixture
def classifier():
    return CommandSafetyClassifier()


def test_read_only_commands(classifier):
    level, cat, _ = classifier.classify("Get-Location")
    assert level == RiskLevel.SAFE
    assert cat == RiskCategory.READ_ONLY

    level, cat, _ = classifier.classify("whoami")
    assert level == RiskLevel.SAFE
    assert cat == RiskCategory.READ_ONLY

    level, cat, _ = classifier.classify("Get-ChildItem -Path C:\\Users")
    assert level == RiskLevel.SAFE
    assert cat == RiskCategory.READ_ONLY


def test_safe_launch_commands(classifier):
    level, cat, _ = classifier.classify("Start-Process 'ms-settings:'")
    assert level == RiskLevel.LOW
    assert cat == RiskCategory.SAFE_ACTION

    level, cat, _ = classifier.classify("Start-Process 'https://www.youtube.com'")
    assert level == RiskLevel.LOW
    assert cat == RiskCategory.SAFE_ACTION

    level, cat, _ = classifier.classify("rundll32.exe user32.dll,LockWorkStation")
    assert level == RiskLevel.LOW
    assert cat == RiskCategory.SAFE_ACTION


def test_data_modification_commands(classifier):
    level, cat, _ = classifier.classify("Remove-Item -Path test.txt")
    assert level == RiskLevel.HIGH
    assert cat == RiskCategory.DATA_MODIFICATION

    level, cat, _ = classifier.classify("del C:\\temp\\file.txt")
    assert level == RiskLevel.HIGH
    assert cat == RiskCategory.DATA_MODIFICATION

    level, cat, _ = classifier.classify("Set-Content -Path out.txt -Value 'hello'")
    assert level == RiskLevel.MEDIUM
    assert cat == RiskCategory.DATA_MODIFICATION


def test_destructive_commands(classifier):
    level, cat, _ = classifier.classify("Format-Volume -DriveLetter D")
    assert level == RiskLevel.CRITICAL
    assert cat == RiskCategory.DESTRUCTIVE


def test_chained_commands(classifier):
    level, cat, _ = classifier.classify("Get-Location; Remove-Item test.txt")
    assert level == RiskLevel.HIGH
    assert cat == RiskCategory.DATA_MODIFICATION
