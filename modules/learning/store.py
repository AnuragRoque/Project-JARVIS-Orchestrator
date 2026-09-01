"""Skill memory: what tool approach worked for a given intent (jarvis.db).

A "skill" = an intent (the user's phrasing, normalized to content tokens) mapped to
the tool call(s) that succeeded, with success/fail counts. It's the generalized,
reactivated form of the terminal module's dormant CommandMemory — keyed by intent,
across *all* tools (not just PowerShell).
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from jarvis.app.data.db import get_database
from jarvis.app.logsetup import get_logger

log = get_logger("learning.store")

# Tiny stopword set so "play the youtube video" ≈ "play youtube video".
_STOP = {
    "the", "a", "an", "to", "please", "can", "you", "could", "would", "my", "me",
    "i", "it", "this", "that", "for", "of", "is", "are", "am", "do", "does", "on",
    "in", "and", "or", "jarvis", "hey", "now", "just", "up", "go", "get", "want",
}
_MIN_JACCARD = 0.5


def _tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


class SkillStore:
    def __init__(self) -> None:
        self.db = get_database()
        self._ensure()

    def _ensure(self) -> None:
        with self.db.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS learned_skills ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, intent_raw TEXT, "
                "intent_tokens TEXT, tools_json TEXT, success_count INTEGER DEFAULT 0, "
                "fail_count INTEGER DEFAULT 0, created_at TEXT, last_used TEXT)")

    # ------------------------------------------------------------- writes
    def record_success(self, intent: str, tools: list[dict]) -> int | None:
        toks = _tokens(intent)
        if not toks or not tools:
            return None
        key = " ".join(sorted(set(toks)))
        now = datetime.now().isoformat(timespec="seconds")
        tools_json = json.dumps(tools, ensure_ascii=False, default=str)
        with self.db.cursor() as cur:
            row = cur.execute(
                "SELECT id FROM learned_skills WHERE intent_tokens = ?", (key,)
            ).fetchone()
            if row:
                cur.execute(
                    "UPDATE learned_skills SET success_count = success_count + 1, "
                    "tools_json = ?, last_used = ? WHERE id = ?",
                    (tools_json, now, row["id"]))
                return row["id"]
            cur.execute(
                "INSERT INTO learned_skills (intent_raw, intent_tokens, tools_json, "
                "success_count, fail_count, created_at, last_used) "
                "VALUES (?,?,?,1,0,?,?)", (intent.strip(), key, tools_json, now, now))
            return cur.lastrowid

    def record_failure(self, intent: str) -> None:
        key = " ".join(sorted(set(_tokens(intent))))
        if not key:
            return
        with self.db.cursor() as cur:
            row = cur.execute(
                "SELECT id, success_count, fail_count FROM learned_skills "
                "WHERE intent_tokens = ?", (key,)).fetchone()
            if not row:
                return
            # Purge if it never really worked; otherwise just down-rank it.
            if row["success_count"] <= 1:
                cur.execute("DELETE FROM learned_skills WHERE id = ?", (row["id"],))
            else:
                cur.execute("UPDATE learned_skills SET fail_count = fail_count + 1 "
                            "WHERE id = ?", (row["id"],))

    # ------------------------------------------------------------- reads
    def best_match(self, intent: str) -> dict | None:
        toks = set(_tokens(intent))
        if not toks:
            return None
        best, best_score = None, 0.0
        with self.db.cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM learned_skills WHERE success_count > fail_count"
            ).fetchall()
        for r in rows:
            stored = set((r["intent_tokens"] or "").split())
            if not stored:
                continue
            jac = len(toks & stored) / len(toks | stored)
            if jac > best_score:
                best, best_score = r, jac
        if best is None or best_score < _MIN_JACCARD:
            return None
        return {
            "id": best["id"], "intent_raw": best["intent_raw"],
            "tools": json.loads(best["tools_json"] or "[]"),
            "success_count": best["success_count"], "fail_count": best["fail_count"],
            "score": round(best_score, 2),
        }

    def list_skills(self, limit: int = 50) -> list[dict]:
        with self.db.cursor() as cur:
            rows = cur.execute(
                "SELECT id, intent_raw, tools_json, success_count, fail_count, "
                "last_used FROM learned_skills ORDER BY success_count DESC, id DESC "
                "LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            tools = json.loads(r["tools_json"] or "[]")
            out.append({"id": r["id"], "intent": r["intent_raw"],
                        "approach": _summarise_tools(tools),
                        "success": r["success_count"], "fail": r["fail_count"],
                        "last_used": r["last_used"]})
        return out

    def forget(self, skill_id: int | None = None, query: str | None = None) -> int:
        with self.db.cursor() as cur:
            if skill_id is not None:
                cur.execute("DELETE FROM learned_skills WHERE id = ?", (int(skill_id),))
                return cur.rowcount
            if query:
                key = f"%{query.strip().lower()}%"
                cur.execute("DELETE FROM learned_skills WHERE lower(intent_raw) LIKE ?",
                            (key,))
                return cur.rowcount
        return 0


def _summarise_tools(tools: list[dict]) -> str:
    bits = []
    for t in tools:
        name = t.get("name", "?")
        args = t.get("args", {})
        if name == "run_python":
            bits.append("run_python(<script>)")
        elif name == "run_powershell":
            bits.append(f"run_powershell: {str(args.get('command',''))[:60]}")
        else:
            bits.append(f"{name}({', '.join(f'{k}={v}' for k, v in list(args.items())[:3])})"[:80])
    return " → ".join(bits)
