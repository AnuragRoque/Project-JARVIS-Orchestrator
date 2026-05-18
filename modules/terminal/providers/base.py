from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class ProviderError(RuntimeError):
    """Base exception raised for AI Provider network or API errors."""


class AIProvider(ABC):
    """Abstract interface for AI Providers (Ollama, OpenAI, etc.)."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """Fetch and return available model names."""

    @abstractmethod
    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Perform a synchronous chat completion.

        Returns a dictionary representing the assistant message object:
        {"role": "assistant", "content": "...", "tool_calls": [...]}
        """

    @abstractmethod
    def chat_stream(self, model: str, messages: list[dict]) -> Iterator[str]:
        """Stream chat completion chunks."""

    @abstractmethod
    def supports_tools(self, model: str) -> bool:
        """Return True if the model natively supports tool/function calls."""
