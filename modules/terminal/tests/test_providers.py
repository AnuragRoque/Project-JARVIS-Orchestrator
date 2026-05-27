import pytest
from jarvis.modules.terminal.providers.base import AIProvider, ProviderError
from jarvis.modules.terminal.providers.ollama_provider import OllamaProvider, parse_text_tool_call, strip_tool_call_noise
from jarvis.modules.terminal.providers.openai_provider import OpenAIProvider


def test_ollama_provider_init():
    provider = OllamaProvider(host="http://localhost:11434")
    assert provider.host == "http://localhost:11434"
    assert provider.supports_tools("llama3.2") is True


def test_parse_text_tool_call():
    content = 'Here is the tool call: <tool_call>{"name": "run_powershell", "arguments": {"command": "Get-Location"}}</tool_call>'
    cmd = parse_text_tool_call(content)
    assert cmd == "Get-Location"


def test_strip_tool_call_noise():
    content = '<tool_call>{"name": "run_powershell", "arguments": {"command": "Get-Location"}}</tool_call>Your current directory is C:\\Users.'
    cleaned = strip_tool_call_noise(content)
    assert cleaned == "Your current directory is C:\\Users."


def test_openai_provider_missing_key():
    provider = OpenAIProvider(api_key="")
    with pytest.raises(ProviderError) as exc_info:
        provider.chat("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    assert "OpenAI API key is missing" in str(exc_info.value)
