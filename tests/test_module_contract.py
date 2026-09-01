"""Module-contract recipe test (Phase 7 acceptance).

Proves the plug-in path: a brand-new module that contributes a tool, a setting,
and a tab becomes usable through the same machinery the shell uses — the
ModuleRegistry and the ToolRouter — with **no edits** to the orchestrator or the
shell. If this passes, dropping a `modules/<id>/module.py` is enough.
"""
from __future__ import annotations

from jarvis.app.registry import AppContext, Module, ModuleRegistry, SettingField, Tool
from jarvis.app.tool_router import ToolRouter

STUB_SPEC = {
    "type": "function",
    "function": {
        "name": "stub_echo",
        "description": "Echo the given text back (contract test).",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
}


class _StubTab:  # a stand-in for a QWidget so the test stays headless
    pass


class StubModule(Module):
    id = "stub"
    name = "Stub"
    version = "1.0.0"

    def __init__(self) -> None:
        self.started = False

    def start(self, ctx: AppContext) -> None:
        self.started = True

    def tools(self) -> list[Tool]:
        return [Tool(STUB_SPEC, self.echo, "read_only")]

    def settings_schema(self) -> list[SettingField]:
        return [SettingField("greeting", "Greeting", "text", "hi")]

    def tab(self):
        return _StubTab()

    def echo(self, text: str = "") -> dict:
        return {"ok": True, "echo": text}


def _ctx(_m) -> AppContext:
    return AppContext(bus=None, db=None, paths=None, settings=None, log=None)


def test_stub_module_plugs_in_without_core_edits():
    reg = ModuleRegistry()
    reg.add(StubModule())
    reg.start_all(_ctx)

    # 1. The module started and contributes a tool.
    tools = reg.all_tools()
    assert any(t.name == "stub_echo" for t in tools)

    # 2. The tool is callable through the SAME router the orchestrator uses.
    router = ToolRouter()
    router.register(tools)
    assert "stub_echo" in router.names()
    result = router.dispatch("stub_echo", {"text": "hello"})
    assert "hello" in result  # dispatch normalises to a string payload

    # 3. Its settings + tab are discoverable for the Settings/shell to render.
    mod = reg.modules()[0]
    schema = mod.settings_schema()
    assert schema and schema[0].key == "greeting"
    assert mod.tab() is not None


def test_registry_discovers_real_modules():
    """discover() imports the shipped modules and collects their tools."""
    reg = ModuleRegistry()
    reg.discover()
    ids = {m.id for m in reg.modules()}
    # The Phase 0–5 modules should all be discoverable.
    assert {"terminal", "timeline", "reminders", "power", "browser"} <= ids
