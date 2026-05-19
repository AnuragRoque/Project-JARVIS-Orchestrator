from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Iterator

from jarvis.modules.terminal.providers.base import AIProvider, ProviderError


def _iter_json_objects(text: str):
    """Yield each balanced {...} substring in text (brace/quote aware)."""
    i, n = 0, len(text)
    while True:
        start = text.find("{", i)
        if start < 0:
            return
        depth = 0
        in_str = escaped = False
        end = -1
        for j in range(start, n):
            ch = text[j]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            return
        yield text[start : end + 1]
        i = end + 1


def _command_from_obj(obj) -> str | None:
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    args = obj.get("arguments") or obj.get("parameters") or obj
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        return None
    command = args.get("command") or args.get("cmd")
    if command and (name in (None, "run_powershell") or "command" in args):
        return command
    return None


def parse_text_tool_call(content: str) -> str | None:
    """Recover run_powershell command from model output formatted as text JSON or tags."""
    if not content:
        return None
    text = content.strip()
    match = re.search(r"<tool_call>\s*(\{.*)</tool_call>", text, re.DOTALL)
    if match:
        text = match.group(1)
    for blob in _iter_json_objects(text):
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        command = _command_from_obj(obj)
        if command:
            return command
    return None


def strip_tool_call_noise(content: str) -> str:
    """Remove leftover tool-call syntax from a final answer."""
    if not content:
        return content
    text = re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL)
    text = re.sub(
        r"```[a-zA-Z_]*\s*\{.*?\}\s*```",
        lambda m: "" if ("run_powershell" in m.group(0) or '"command"' in m.group(0)) else m.group(0),
        text,
        flags=re.DOTALL,
    )
    for blob in list(_iter_json_objects(text)):
        if "run_powershell" in blob or '"command"' in blob:
            text = text.replace(blob, "")
    return text.strip()


class OllamaProvider(AIProvider):
    """Implementation of AIProvider for local Ollama instances."""

    def __init__(self, host: str = "http://localhost:11434", timeout: float = 300.0) -> None:
        self.host = host.strip().rstrip("/")
        if not self.host.startswith(("http://", "https://")):
            self.host = "http://" + self.host
        self.timeout = timeout
        self._tools_capable: set[str] = set()

    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def list_models(self) -> list[str]:
        try:
            req = urllib.request.Request(self._url("/api/tags"))
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderError(
                f"Can't reach Ollama at {self.host} — is it running? ({exc})"
            ) from exc

        models: list[str] = []
        self._tools_capable = set()
        for entry in data.get("models", []):
            caps = entry.get("capabilities") or []
            if caps and "completion" not in caps:
                continue
            name = entry.get("name")
            if not name:
                continue
            models.append(name)
            if "tools" in caps:
                self._tools_capable.add(name)
        return sorted(models)

    def supports_tools(self, model: str) -> bool:
        return model in self._tools_capable or True  # fallback text tool parsing allows tool use

    def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {"model": model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        req = urllib.request.Request(
            self._url("/api/chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise ProviderError(f"Ollama returned HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderError(f"Can't reach Ollama at {self.host} — {exc}") from exc

        if isinstance(obj, dict) and obj.get("error"):
            raise ProviderError(str(obj["error"]))
        return obj.get("message", {}) if isinstance(obj, dict) else {}

    def chat_stream(self, model: str, messages: list[dict]) -> Iterator[str]:
        payload = json.dumps(
            {"model": model, "messages": messages, "stream": True}
        ).encode("utf-8")
        req = urllib.request.Request(
            self._url("/api/chat"),
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise ProviderError(f"Ollama returned HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ProviderError(f"Can't reach Ollama at {self.host} — {exc}") from exc

        with resp:
            for raw in resp:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "error" in obj:
                    raise ProviderError(str(obj["error"]))
                chunk = (obj.get("message") or {}).get("content")
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break
