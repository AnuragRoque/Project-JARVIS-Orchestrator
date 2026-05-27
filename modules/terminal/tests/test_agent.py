import pytest
from PyQt6.QtWidgets import QApplication
from jarvis.modules.terminal.agent.agent import Agent, infer_action_command
from jarvis.modules.terminal.core.models import CommandResult
from jarvis.modules.terminal.providers.base import AIProvider

app = QApplication.instance() or QApplication([])


class MockProvider(AIProvider):
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.call_count = 0

    def list_models(self) -> list[str]:
        return ["mock-model"]

    def supports_tools(self, model: str) -> bool:
        return True

    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return {"role": "assistant", "content": "Done"}

    def chat_stream(self, model: str, messages: list[dict]):
        yield "Done"


def test_infer_action_command():
    assert infer_action_command("open setting") == 'Start-Process "ms-settings:"'
    assert infer_action_command("simulate win+i") == 'Start-Process "ms-settings:"'
    assert infer_action_command("open youtube") == 'Start-Process "https://www.youtube.com"'
    assert infer_action_command("open edge browser") == 'Start-Process "msedge"'
    assert infer_action_command("lock pc") == 'rundll32.exe user32.dll,LockWorkStation'
    assert infer_action_command("what is the weather") is None


def test_agent_single_tool_execution():
    responses = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {"name": "run_powershell", "arguments": {"command": "Get-Location"}},
                }
            ],
        },
        {"role": "assistant", "content": "Current directory is C:\\Users"},
    ]
    provider = MockProvider(responses)
    agent = Agent(provider, "mock-model", [{"role": "user", "content": "where am i"}])

    commands_run = []

    def handle_request(cmd):
        commands_run.append(cmd)
        agent.provide_result(CommandResult(success=True, stdout="C:\\Users"))

    agent.request_command.connect(handle_request)

    final_text = []
    agent.final.connect(lambda txt: final_text.append(txt))

    agent.run()

    assert "Get-Location" in commands_run
    assert len(final_text) == 1
    assert "C:\\Users" in final_text[0]


def test_agent_intent_fallback_execution():
    # Model returns plain text WITHOUT tool calls for "open setting"
    responses = [
        {"role": "assistant", "content": "Windows Settings has been opened."}
    ]
    provider = MockProvider(responses)
    agent = Agent(provider, "mock-model", [{"role": "user", "content": "open setting"}])

    commands_run = []
    agent.request_command.connect(lambda cmd: commands_run.append(cmd))
    agent.request_command.connect(lambda cmd: agent.provide_result(CommandResult(success=True, stdout="")))

    agent.run()

    assert 'Start-Process "ms-settings:"' in commands_run


def test_agent_loop_detection():
    responses = [
        {"role": "assistant", "tool_calls": [{"function": {"name": "run_powershell", "arguments": {"command": "Get-Item X"}}}]},
        {"role": "assistant", "tool_calls": [{"function": {"name": "run_powershell", "arguments": {"command": "Get-Item X"}}}]},
        {"role": "assistant", "tool_calls": [{"function": {"name": "run_powershell", "arguments": {"command": "Get-Item X"}}}]},
    ]
    provider = MockProvider(responses)
    agent = Agent(provider, "mock-model", [{"role": "user", "content": "find X"}])

    agent.request_command.connect(lambda cmd: agent.provide_result(CommandResult(success=False, stdout="Path not found")))

    final_text = []
    agent.final.connect(lambda txt: final_text.append(txt))

    agent.run()

    assert len(final_text) == 1
    assert "LOOP_DETECTED" in final_text[0]
