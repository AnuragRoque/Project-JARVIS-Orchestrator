"""Learning module: owns the skill memory + learner, exposes inspect/forget tools.

The learning itself happens via the learner hooks the voice controller calls each
turn (hint injection + outcome recording). These tools just let the user (and the
model) see and prune what's been learned.
"""
from __future__ import annotations

from jarvis.app.logsetup import get_logger
from jarvis.app.registry import AppContext, Module, SettingField, Tool
from .learner import SkillLearner
from .store import SkillStore

log = get_logger("module.learning")

LIST_SKILLS_SPEC = {
    "type": "function",
    "function": {
        "name": "list_skills",
        "description": "List what JARVIS has learned — the approaches it remembers "
                       "worked for past requests (intent → tool used, success/fail).",
        "parameters": {"type": "object", "properties": {}},
    },
}

FORGET_SKILL_SPEC = {
    "type": "function",
    "function": {
        "name": "forget_skill",
        "description": "Forget a learned approach by its id (from list_skills) or by "
                       "matching words in the request it was learned for.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "query": {"type": "string"},
            },
        },
    },
}


class LearningModule(Module):
    id = "learning"
    name = "Learning"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store: SkillStore | None = None
        self.learner: SkillLearner | None = None

    def start(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self.store = SkillStore()
        self.learner = SkillLearner(self.store)

    def tools(self) -> list[Tool]:
        return [
            Tool(LIST_SKILLS_SPEC, self.list_skills, "read_only"),
            Tool(FORGET_SKILL_SPEC, self.forget_skill, "safe_action"),
        ]

    def settings_schema(self) -> list[SettingField]:
        return [SettingField("enabled", "Learn from what works (reuse it next time)",
                             "bool", True)]

    # ------------------------------------------------------------- handlers
    def list_skills(self) -> dict:
        rows = self.store.list_skills() if self.store else []
        return {"count": len(rows), "skills": rows}

    def forget_skill(self, id: int | None = None, query: str | None = None) -> dict:
        if not self.store:
            return {"ok": False, "error": "Learning store unavailable."}
        n = self.store.forget(skill_id=id, query=query)
        return {"ok": n > 0, "removed": n,
                "message": f"Forgot {n} learned approach(es)." if n else "Nothing matched."}


def get_module() -> Module:
    return LearningModule()
