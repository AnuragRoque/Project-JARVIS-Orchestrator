"""The learning loop: save the approach that worked, avoid the one that failed.

Wired into the voice controller around each orchestrated turn:
- ``note_turn`` (after a turn): if tools ran without error, provisionally save the
  approach as a skill for that intent.
- ``apply_feedback`` (start of next turn): read the user's reaction to the *previous*
  turn — "try again"/"didn't work" purges/avoids that approach; "yes"/"good" boosts it.
- ``hint_for`` (start of a turn): return a MEMORY note to inject into the model's
  context — the proven approach to reuse, and any approach to avoid this time.
"""
from __future__ import annotations

import json
import re

from jarvis.app.logsetup import get_logger
from .store import SkillStore

log = get_logger("learning.learner")

_NEG = ("try again", "try something", "didn't work", "did not work", "doesnt work",
        "does not work", "not working", "didnt work", "not work", "failed", "wrong",
        "nope", "not that", "that's not", "thats not", "different way", "still not",
        "isn't working", "isnt working", "no it", "that didn't", "that didnt")
_POS = ("thanks", "thank you", "perfect", "worked", "works", "good job", "great",
        "nice", "correct", "awesome", "that worked", "yes that", "well done",
        "good", "cool", "brilliant")


def classify_feedback(text: str) -> str:
    """'negative' | 'positive' | 'neutral' — the user's reaction to the last turn."""
    low = (text or "").strip().lower()
    if not low:
        return "neutral"
    if any(p in low for p in _NEG):
        return "negative"
    # Only treat as positive if the message is short/reactive (not a new request).
    if len(low.split()) <= 4 and any(p in low for p in _POS):
        return "positive"
    return "neutral"


class SkillLearner:
    def __init__(self, store: SkillStore | None = None) -> None:
        self.store = store or SkillStore()
        self._pending: dict | None = None   # last turn's saved approach
        self._avoid: dict | None = None      # approach to steer away from this turn

    # ------------------------------------------------- after a turn completes
    def note_turn(self, prompt: str, tools: list[dict], had_error: bool) -> None:
        self._avoid = None
        if had_error or not tools:
            self._pending = None
            return
        try:
            self.store.record_success(prompt, tools)
            self._pending = {"intent": prompt, "tools": tools}
        except Exception:
            log.debug("record_success failed", exc_info=True)
            self._pending = None

    # ------------------------------------------------- start of next turn
    def apply_feedback(self, prompt: str) -> None:
        if self._pending is None:
            return
        verdict = classify_feedback(prompt)
        try:
            if verdict == "negative":
                self.store.record_failure(self._pending["intent"])
                self._avoid = dict(self._pending)   # steer away on the retry
                log.info("Skill down-ranked (user said it failed): %s",
                         self._pending["intent"][:60])
                self._pending = None
            elif verdict == "positive":
                self.store.record_success(self._pending["intent"], self._pending["tools"])
                log.info("Skill confirmed by user: %s", self._pending["intent"][:60])
                self._pending = None
        except Exception:
            log.debug("apply_feedback failed", exc_info=True)

    def hint_for(self, prompt: str) -> str | None:
        parts: list[str] = []
        if self._avoid:
            parts.append("MEMORY — the approach you just tried did NOT work for this "
                         "request (" + _summ(self._avoid["tools"]) + "). Use a "
                         "DIFFERENT approach now (usually run_python).")
        try:
            match = self.store.best_match(prompt)
        except Exception:
            match = None
        if match and (not self._avoid or match["intent_raw"] != self._avoid["intent"]):
            parts.append(
                "MEMORY — a similar request worked before ('" + match["intent_raw"][:80]
                + "'). What worked: " + _detail(match["tools"])
                + " Reuse this exact approach first unless the user wants something else.")
        return "\n".join(parts) if parts else None


def _summ(tools: list[dict]) -> str:
    return ", ".join(t.get("name", "?") for t in tools) or "that tool"


def _detail(tools: list[dict]) -> str:
    """Compact, reusable description of the winning tool call(s) — includes code."""
    bits = []
    for t in tools:
        name = t.get("name", "?")
        args = t.get("args", {}) or {}
        if name == "run_python":
            code = str(args.get("code", ""))[:600]
            bits.append(f"run_python with this code:\n```python\n{code}\n```")
        elif name == "run_powershell":
            bits.append(f"run_powershell: `{str(args.get('command',''))[:120]}`")
        else:
            try:
                a = json.dumps(args, ensure_ascii=False, default=str)[:160]
            except Exception:
                a = str(args)[:160]
            bits.append(f"{name} with args {a}")
    return " then ".join(bits)
