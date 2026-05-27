import tempfile
from pathlib import Path
import pytest
from jarvis.modules.terminal.core.models import MatchConfidence
from jarvis.modules.terminal.memory.command_memory import CommandMemory
from jarvis.modules.terminal.memory.database import DatabaseManager
from jarvis.modules.terminal.memory.matcher import PatternMatcher


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_memory.db"
        db_mgr = DatabaseManager(db_path)
        memory = CommandMemory(db_mgr)
        yield memory


def test_pattern_generalization():
    pattern, template, param_count = PatternMatcher.generalize_prompt_and_cmd(
        "shutdown in 20 sec", "shutdown /s /t 20"
    )
    assert r"(\d+)" in pattern
    assert "{1}" in template
    assert param_count == 1


def test_memory_save_and_match(temp_db):
    temp_db.save_command("shutdown in 20 sec", "shutdown /s /t 20", success=True)

    match = temp_db.find_match("turn off in 30 sec")
    assert match is not None
    assert match.command == "shutdown /s /t 30"
    assert match.confidence in (MatchConfidence.EXACT, MatchConfidence.HIGH)


def test_greetings_never_match_memory(temp_db):
    temp_db.save_command("shutdown in 20 sec", "shutdown /s /t 20", success=True)
    match = temp_db.find_match("hey")
    assert match is None
    match_who = temp_db.find_match("who are you")
    assert match_who is None


def test_failed_command_not_saved(temp_db):
    temp_db.save_command("shutdown in 20 sec", "[DECLINED] Command denied", success=False)
    match = temp_db.find_match("shutdown in 20 sec")
    assert match is None


def test_false_positive_rejection(temp_db):
    temp_db.save_command("show files in Downloads", "Get-ChildItem $HOME\\Downloads", success=True)
    match = temp_db.find_match("delete files in Downloads")
    assert match is None
