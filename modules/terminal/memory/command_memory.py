from __future__ import annotations

import re
from datetime import datetime
from jarvis.modules.terminal.config.settings import settings
from jarvis.modules.terminal.core.logging import logger
from jarvis.modules.terminal.core.models import MatchConfidence, MemoryMatch, RiskCategory, RiskLevel
from jarvis.modules.terminal.memory.database import DatabaseManager
from jarvis.modules.terminal.memory.matcher import PatternMatcher
from jarvis.modules.terminal.permissions.safety import CommandSafetyClassifier

GREETINGS_AND_CONVERSATIONAL = {
    "hey", "hi", "hello", "good morning", "good evening", "thanks", "thank you",
    "who are you", "what is your name", "bye", "exit", "yes", "no", "sure", "ok", "okay"
}


class CommandMemory:
    """SQLite-backed memory engine for fast-path command matching and safe learning."""

    def __init__(self, db_manager: DatabaseManager | None = None) -> None:
        self.db_manager = db_manager or DatabaseManager()
        self.matcher = PatternMatcher()
        self.classifier = CommandSafetyClassifier()

    def save_command(
        self,
        prompt: str,
        command: str,
        success: bool = True,
    ) -> None:
        """Store command into memory ONLY if execution was allowed and succeeded."""
        if not settings.memory_enabled:
            return

        if not prompt or not command or not success:
            return

        p_clean = prompt.strip().lower()
        if p_clean in GREETINGS_AND_CONVERSATIONAL:
            return

        cmd_clean = command.strip()
        if (
            cmd_clean.startswith(("[BLOCKED]", "[DECLINED]", "[terminal]", "[LOOP_DETECTED]"))
            or "[stopped" in cmd_clean
            or "timed out" in cmd_clean.lower()
            or "is not recognized" in cmd_clean.lower()
        ):
            return

        pattern_str, cmd_template, param_count = self.matcher.generalize_prompt_and_cmd(prompt, cmd_clean)
        risk_level, risk_category, _ = self.classifier.classify(cmd_clean)
        now = datetime.now().isoformat()

        with self.db_manager.get_connection() as conn:
            cur = conn.execute("SELECT id, use_count FROM saved_commands WHERE prompt_pattern = ?", (pattern_str,))
            row = cur.fetchone()

            if row:
                conn.execute(
                    """UPDATE saved_commands 
                       SET use_count = use_count + 1, 
                           success_count = success_count + 1, 
                           last_used = ? 
                       WHERE id = ?""",
                    (now, row["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO saved_commands (
                        raw_prompt, prompt_pattern, command_template, param_count,
                        risk_category, risk_level, use_count, success_count, created_at, last_used
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?)""",
                    (
                        prompt.strip(),
                        pattern_str,
                        cmd_template,
                        param_count,
                        risk_category.value,
                        risk_level.value,
                        now,
                        now,
                    ),
                )
            conn.commit()
            logger.info(f"Learned command pattern into memory: '{prompt}' -> '{cmd_template}'")

    def find_match(self, prompt: str) -> MemoryMatch | None:
        """Find candidate fast-path memory match. Validates confidence and reclassifies safety."""
        if not settings.memory_enabled or not prompt or not prompt.strip():
            return None

        p_clean = prompt.strip().lower()
        if p_clean in GREETINGS_AND_CONVERSATIONAL:
            return None

        with self.db_manager.get_connection() as conn:
            cur = conn.execute(
                """SELECT id, raw_prompt, prompt_pattern, command_template, param_count, risk_level
                   FROM saved_commands 
                   ORDER BY use_count DESC, id DESC"""
            )
            rows = cur.fetchall()

            for row in rows:
                pattern = row["prompt_pattern"]
                try:
                    match = re.match(pattern, p_clean, re.IGNORECASE)
                except re.error:
                    continue

                if match:
                    confidence = self.matcher.evaluate_confidence(p_clean, row["raw_prompt"], pattern)
                    if confidence not in (MatchConfidence.EXACT, MatchConfidence.HIGH):
                        continue

                    groups = match.groups()
                    populated_cmd = self.matcher.populate_template(row["command_template"], groups)

                    # RECLASSIFY populated candidate command with safety classifier
                    risk_level, _, _ = self.classifier.classify(populated_cmd)

                    now = datetime.now().isoformat()
                    conn.execute(
                        "UPDATE saved_commands SET use_count = use_count + 1, last_used = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    conn.commit()

                    return MemoryMatch(
                        command=populated_cmd,
                        prompt_pattern=pattern,
                        match_id=row["id"],
                        confidence=confidence,
                        risk_level=risk_level,
                        param_count=row["param_count"],
                    )

        return None

    def purge_command(self, match_id: int) -> None:
        """Purge bad command from database when execution fails."""
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM saved_commands WHERE id = ?", (match_id,))
            conn.commit()
            logger.info(f"Purged invalid memory match id {match_id}")

    def record_failure(self, match_id: int) -> None:
        self.purge_command(match_id)

    def clear_all(self) -> None:
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM saved_commands;")
            conn.commit()
