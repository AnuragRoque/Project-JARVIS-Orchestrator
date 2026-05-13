from __future__ import annotations

import re
from jarvis.modules.terminal.core.models import MatchConfidence

SYNONYM_GROUPS = [
    {"shutdown", "turn off", "power off", "switch off"},
    {"reboot", "restart", "reset"},
    {"list", "show", "get", "display", "find"},
    {"sec", "seconds", "s"},
    {"min", "minutes", "m"},
    {"hr", "hours", "h"},
]

# Build map from individual words / multi-words to group representative
SYNONYM_MAP: dict[str, str] = {}
for group in SYNONYM_GROUPS:
    canonical = sorted(group, key=len, reverse=True)[0]
    for phrase in group:
        SYNONYM_MAP[phrase] = canonical


def _canonicalize_phrase(text: str) -> str:
    text_lower = text.lower()
    for phrase, canonical in SYNONYM_MAP.items():
        text_lower = re.sub(r"\b" + re.escape(phrase) + r"\b", canonical, text_lower)
    return text_lower


def _build_synonym_regex(word: str) -> str:
    word_lower = word.lower()
    for group in SYNONYM_GROUPS:
        if word_lower in group:
            pattern = "|".join(re.escape(w) for w in sorted(group, key=len, reverse=True))
            return f"(?:{pattern})"
    return re.escape(word)


class PatternMatcher:
    """Handles parameter extraction, regex pattern generation, and confidence scoring."""

    @staticmethod
    def generalize_prompt_and_cmd(prompt: str, command: str) -> tuple[str, str, int]:
        p_clean = prompt.strip().lower()
        c_clean = command.strip()

        num_matches = list(re.finditer(r"\b\d+\b", p_clean))
        param_count = 0
        cmd_template = c_clean

        for i, match in enumerate(num_matches, 1):
            num_str = match.group(0)
            if num_str in c_clean:
                param_count += 1
                cmd_template = re.sub(r"\b" + re.escape(num_str) + r"\b", f"{{{i}}}", cmd_template)

        tokens = re.split(r"(\b\d+\b|\s+|[^\w\s])", p_clean)
        regex_parts = []
        for token in tokens:
            if not token:
                continue
            if re.match(r"^\d+$", token):
                regex_parts.append(r"(\d+)")
            elif re.match(r"^\s+$", token):
                regex_parts.append(r"\s+")
            elif re.match(r"^\w+$", token):
                regex_parts.append(_build_synonym_regex(token))
            else:
                regex_parts.append(re.escape(token))

        pattern_str = r"^(?:can you|please|could you|jarvis)?\s*" + "".join(regex_parts) + r"\s*\??$"
        return pattern_str, cmd_template, param_count

    @staticmethod
    def populate_template(template: str, groups: tuple[str, ...]) -> str:
        populated = template
        for idx, val in enumerate(groups, 1):
            populated = populated.replace(f"{{{idx}}}", val)
        return populated

    @staticmethod
    def evaluate_confidence(prompt: str, raw_saved_prompt: str, pattern: str) -> MatchConfidence:
        p_clean = prompt.strip().lower()
        r_clean = raw_saved_prompt.strip().lower()

        if p_clean == r_clean:
            return MatchConfidence.EXACT

        # Canonicalize phrases using synonym groups before calculating overlap
        p_canon = _canonicalize_phrase(p_clean)
        r_canon = _canonicalize_phrase(r_clean)

        p_words = set(re.findall(r"\w+", p_canon))
        r_words = set(re.findall(r"\w+", r_canon))

        if not p_words or not r_words:
            return MatchConfidence.LOW

        # Ensure action verbs match if both prompts contain verbs
        critical_verbs = {"delete", "remove", "clear", "format", "shutdown", "reboot", "list", "show", "get"}
        p_verbs = p_words.intersection(critical_verbs)
        r_verbs = r_words.intersection(critical_verbs)
        if p_verbs and r_verbs and not p_verbs.intersection(r_verbs):
            return MatchConfidence.LOW

        # Ignore numbers when computing word ratio overlap
        p_text_words = {w for w in p_words if not w.isdigit()}
        r_text_words = {w for w in r_words if not w.isdigit()}

        if not p_text_words or not r_text_words:
            return MatchConfidence.HIGH

        overlap = len(p_text_words.intersection(r_text_words)) / max(len(p_text_words), len(r_text_words))
        if overlap >= 0.75:
            return MatchConfidence.HIGH
        elif overlap >= 0.5:
            return MatchConfidence.MEDIUM
        return MatchConfidence.LOW
