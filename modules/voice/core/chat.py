"""Chat completion via the OpenAI API — streamed for minimum latency."""
from __future__ import annotations

from typing import Callable, Iterable

from openai import OpenAI

_clients: dict[str, OpenAI] = {}


def _client(api_key: str) -> OpenAI:
    """Reuse one OpenAI client per key (avoids per-request connection setup)."""
    if not api_key:
        raise RuntimeError("Missing OpenAI API key. Add it in Settings.")
    client = _clients.get(api_key)
    if client is None:
        client = OpenAI(api_key=api_key)
        _clients[api_key] = client
    return client


def _messages(prompt: str, system_prompt: str, history: list[dict] | None) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": system_prompt}]
    if history:
        msgs.extend(history)
    msgs.append({"role": "user", "content": prompt})
    return msgs


def stream(prompt: str, api_key: str, model: str, system_prompt: str,
           history: list[dict] | None = None,
           on_chunk: Callable[[str], None] | None = None) -> str:
    """Stream the reply, calling `on_chunk` with each delta. Returns full text."""
    client = _client(api_key)
    parts: list[str] = []
    resp: Iterable = client.chat.completions.create(
        model=model,
        messages=_messages(prompt, system_prompt, history),
        stream=True,
    )
    for event in resp:
        if not event.choices:
            continue
        delta = event.choices[0].delta.content or ""
        if delta:
            parts.append(delta)
            if on_chunk:
                on_chunk(delta)
    return "".join(parts).strip()


def ask(prompt: str, api_key: str, model: str, system_prompt: str,
        history: list[dict] | None = None) -> str:
    """Non-streaming convenience wrapper."""
    resp = _client(api_key).chat.completions.create(
        model=model, messages=_messages(prompt, system_prompt, history),
    )
    return (resp.choices[0].message.content or "").strip()
