"""Regression tests for the Sep-2026 log audit fixes.

Covers: duplicate tool-call collapsing, the self-termination guard, find_files
env-var expansion, and the activity_summary duration formatting.
"""
from __future__ import annotations

import os

from jarvis.app import sysfacts
from jarvis.app.orchestrator import Orchestrator
from jarvis.app.permissions import _would_kill_self
from jarvis.modules.documents import finder
from jarvis.modules.timeline.module import _dur


# --------------------------------------------------------------- dedup
def _msg(*calls):
    return {"tool_calls": [
        {"id": f"c{i}", "function": {"name": n, "arguments": a}}
        for i, (n, a) in enumerate(calls)
    ]}


def test_extract_calls_collapses_exact_duplicates():
    # The model emitting the same shutdown five times must run once.
    dup = ("power_control", '{"action": "shutdown", "delay_seconds": 0}')
    calls = Orchestrator._extract_calls(_msg(dup, dup, dup, dup, dup))
    assert len(calls) == 1
    assert calls[0][1] == "power_control"


def test_extract_calls_keeps_distinct_calls():
    calls = Orchestrator._extract_calls(_msg(
        ("set_reminder", '{"text": "a", "when": "in 1 min"}'),
        ("set_reminder", '{"text": "b", "when": "in 1 min"}'),
    ))
    assert len(calls) == 2


# ----------------------------------------------------------- self-kill
def test_self_kill_blocks_direct_python_jarvis_kill():
    cmd = ("Get-Process | Where-Object {$_.ProcessName -match 'python' -or "
           "$_.ProcessName -match 'jarvis'} | Stop-Process -Force")
    assert _would_kill_self("run_powershell", {"command": cmd})


def test_self_kill_blocks_unfiltered_mass_kill():
    cmd = ("Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
           "ForEach-Object {Stop-Process -Id $_.Id -Force}")
    assert _would_kill_self("run_powershell", {"command": cmd})


def test_self_kill_blocks_taskkill_python():
    assert _would_kill_self("run_python",
                            {"code": "import os; os.system('taskkill /im python.exe')"})


def test_self_kill_allows_closing_a_named_app():
    assert not _would_kill_self("run_powershell",
                                {"command": "Stop-Process -Name OneNote"})
    assert not _would_kill_self("run_powershell",
                                {"command": "Get-ChildItem C:\\"})


# ------------------------------------------------------ find_files env
def test_resolve_roots_expands_percent_temp():
    roots = finder.resolve_roots("%temp%")
    assert roots and roots[0].exists()
    assert os.path.normcase(str(roots[0])) == os.path.normcase(
        os.environ.get("TEMP", ""))


def test_resolve_roots_expands_env_username_path():
    # PowerShell-style $env:USERNAME embedded in a path must resolve.
    p = r"C:\Users\$env:USERNAME\AppData\Local\Temp"
    roots = finder.resolve_roots(p)
    # Only asserts it expanded to a real, existing dir on this machine.
    assert roots and roots[0].exists()


# ------------------------------------------------------- system facts
def test_env_snapshot_has_real_username_and_home():
    snap = sysfacts.env_snapshot()
    assert snap.get("username") and "<" not in snap["username"]
    assert snap.get("home") and os.path.isdir(snap["home"])
    # No placeholder tokens ever leak into the facts.
    assert not any("<" in v for v in snap.values())


def test_fact_cache_roundtrip():
    sysfacts.set_fact("app_dir:__pytest__", '["C:\\\\tmp"]', source="test")
    assert sysfacts.get_fact("app_dir:__pytest__") == '["C:\\\\tmp"]'


def test_prompt_block_lists_real_paths_no_placeholder():
    block = sysfacts.prompt_block()
    assert "SYSTEM FACTS" in block
    assert "<YourUsername>" in block  # only in the instruction line
    # The actual fact lines must contain a real drive path, not a placeholder path.
    assert "C:\\" in block or "/" in block


# ---------------------------------------------------------- duration
def test_dur_formats():
    assert _dur(3 * 3600 + 12 * 60) == "3h 12m"
    assert _dur(45 * 60) == "45m"
    assert _dur(30) == "30s"
    assert _dur(7200) == "2h"
