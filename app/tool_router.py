"""Aggregates module tools for the orchestrator and dispatches calls.

The router holds every :class:`Tool` a module contributes. It exposes the OpenAI
function specs (the array passed to ``provider.chat``) and dispatches a chosen
call to the owning handler, normalising the result to compact text for the next
LLM step.
"""
from __future__ import annotations

import json
from typing import Any

from .logsetup import get_logger
from .registry import Tool

log = get_logger("tools")

MAX_RESULT_CHARS = 4000


class ToolRouter:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tools: list[Tool]) -> None:
        for t in tools:
            if not t.name:
                continue
            self._tools[t.name] = t
            log.info("Registered tool %s (risk=%s)", t.name, t.risk)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict]:
        return [t.spec for t in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """Run a tool by name and return a normalised text result."""
        tool = self._tools.get(name)
        if tool is None:
            return f"[error] Unknown tool '{name}'."
        try:
            result = tool.handler(**(args or {}))
        except TypeError as exc:
            return f"[error] Bad arguments for '{name}': {exc}"
        except Exception as exc:  # handler errors never crash the loop
            log.exception("Tool %s failed", name)
            return f"[error] Tool '{name}' failed: {exc}"
        return self._normalise(result)

    @staticmethod
    def _normalise(result: Any) -> str:
        if result is None:
            return "(no result)"
        if isinstance(result, str):
            text = result
        else:
            try:
                text = json.dumps(result, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                text = str(result)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + "\n…[truncated]"
        return text
