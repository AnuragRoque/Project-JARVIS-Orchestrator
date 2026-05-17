from __future__ import annotations

import json
from typing import Iterator

try:
    import openai
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.providers.base import AIProvider, ProviderError


class OpenAIProvider(AIProvider):
    """Implementation of AIProvider for OpenAI / ChatGPT API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        if not HAS_OPENAI:
            raise ProviderError("The 'openai' package is not installed. Run `pip install openai`.")
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_base_url
        self.default_model = model or settings.openai_model
        
        if not self.api_key:
            # We allow creation even without key, but calls will raise ProviderError with a clear instruction
            self._client = None
        else:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _ensure_client(self) -> OpenAI:
        if not self._client:
            if not self.api_key:
                raise ProviderError(
                    "OpenAI API key is missing. Set OPENAI_API_KEY in your .env file."
                )
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def list_models(self) -> list[str]:
        if not self.api_key:
            return [self.default_model]
        try:
            client = self._ensure_client()
            models_res = client.models.list()
            # Filter chat models
            chat_models = [
                m.id for m in models_res.data
                if "gpt" in m.id or "o1" in m.id or "o3" in m.id
            ]
            return sorted(chat_models) if chat_models else [self.default_model]
        except Exception as exc:
            # Fallback to configured model if list fails
            return [self.default_model]

    def supports_tools(self, model: str) -> bool:
        return True

    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict:
        client = self._ensure_client()
        target_model = model or self.default_model
        
        # Adapt messages to OpenAI format. Assistant messages that requested
        # tools MUST carry their tool_calls, and each tool result MUST reference
        # the matching tool_call_id — otherwise the API rejects the follow-up.
        formatted_messages = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id") or "call_default",
                    "content": str(msg.get("content", "")),
                })
            elif role == "assistant" and msg.get("tool_calls"):
                formatted_messages.append({
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": msg["tool_calls"],
                })
            else:
                formatted_messages.append({
                    "role": role,
                    "content": msg.get("content", ""),
                })

        kwargs: dict = {
            "model": target_model,
            "messages": formatted_messages,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            result: dict = {
                "role": "assistant",
                "content": message.content or "",
            }

            if message.tool_calls:
                tool_calls_list = []
                for tc in message.tool_calls:
                    tool_calls_list.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
                result["tool_calls"] = tool_calls_list

            return result
        except Exception as exc:
            raise ProviderError(f"OpenAI API request failed: {exc}") from exc

    def chat_stream(self, model: str, messages: list[dict]) -> Iterator[str]:
        client = self._ensure_client()
        target_model = model or self.default_model

        formatted_messages = [
            {"role": m.get("role"), "content": m.get("content", "")}
            for m in messages
            if m.get("role") in ("system", "user", "assistant")
        ]

        try:
            stream = client.chat.completions.create(
                model=target_model,
                messages=formatted_messages,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise ProviderError(f"OpenAI streaming failed: {exc}") from exc
