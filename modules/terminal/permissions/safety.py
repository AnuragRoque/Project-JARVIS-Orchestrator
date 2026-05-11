from __future__ import annotations

import re
from jarvis.modules.terminal.core.models import RiskCategory, RiskLevel


# Read-only verbs and utilities
READ_ONLY_PREFIXES = (
    "get-", "select-", "test-", "measure-", "show-", "out-string",
    "export-clixml", "compare-", "format-list", "format-table"
)
READ_ONLY_COMMANDS = {
    "whoami", "hostname", "ipconfig", "ping", "dir", "ls", "pwd", "cd",
    "cat", "echo", "type", "ver", "systeminfo", "tasklist", "driverquery"
}

# Safe user actions (e.g. launching non-destructive applications, websites, settings, locking workstation)
SAFE_LAUNCH_COMMANDS = {
    "start-process", "invoke-item", "explorer", "explorer.exe",
    "notepad", "notepad.exe", "calc", "calc.exe", "code", "msedge", "chrome",
    "rundll32.exe", "rundll32"
}

# Risk patterns paired with category, risk level, and human explanation
RISK_RULES = [
    # Disk formatting / partitioning -> CRITICAL / DESTRUCTIVE
    (
        r"\bFormat-Volume\b|\bClear-Disk\b|\bRemove-Partition\b|\bdiskpart\b|\bformat\.com\b",
        RiskCategory.DESTRUCTIVE,
        RiskLevel.CRITICAL,
        "Disk or partition formatting operation",
    ),
    # Registry modifications -> SYSTEM_MODIFICATION / HIGH
    (
        r"\bSet-ItemProperty\b|\bNew-ItemProperty\b|\bRemove-ItemProperty\b|\breg\s+(add|delete|import|restore)\b",
        RiskCategory.SYSTEM_MODIFICATION,
        RiskLevel.HIGH,
        "Windows Registry modification",
    ),
    # Security & Execution policy -> SECURITY_MODIFICATION / HIGH
    (
        r"\bSet-ExecutionPolicy\b|\bnetsh\b|\bbcdedit\b|\btakeown\b|\bicacls\b",
        RiskCategory.SECURITY_MODIFICATION,
        RiskLevel.HIGH,
        "System security or execution policy modification",
    ),
    # System shutdown / reboot -> PROCESS_CONTROL / HIGH
    (
        r"\bStop-Computer\b|\bRestart-Computer\b|\bshutdown\b",
        RiskCategory.PROCESS_CONTROL,
        RiskLevel.HIGH,
        "System shutdown or restart",
    ),
    # Process / Service termination -> PROCESS_CONTROL / MEDIUM
    (
        r"\bStop-Process\b|(?<![\w-])kill\b|\btaskkill\b|\bStop-Service\b|\bRestart-Service\b|\bSet-Service\b|\bRemove-Service\b",
        RiskCategory.PROCESS_CONTROL,
        RiskLevel.MEDIUM,
        "Terminating or modifying running processes/services",
    ),
    # File / Folder Deletion -> DATA_MODIFICATION / HIGH
    (
        r"\bRemove-Item\b|\bri\b|\brd\b|\brmdir\b|\bdel\b|\berase\b|\bunlink\b|(?<![\w-])rm\b",
        RiskCategory.DATA_MODIFICATION,
        RiskLevel.HIGH,
        "File or directory deletion",
    ),
    # File writing / Output redirection -> DATA_MODIFICATION / MEDIUM
    (
        r"\bSet-Content\b|\bAdd-Content\b|\bOut-File\b|\bTee-Object\b|>>?",
        RiskCategory.DATA_MODIFICATION,
        RiskLevel.MEDIUM,
        "Writing or overwriting files",
    ),
    # File Movement / Renaming -> DATA_MODIFICATION / LOW
    (
        r"\bMove-Item\b|\bRename-Item\b|(?<![\w-])mv\b|(?<![\w-])rni\b|\bren\b|\brename\b|\bmove\b",
        RiskCategory.DATA_MODIFICATION,
        RiskLevel.LOW,
        "Moving or renaming files/directories",
    ),
    # Copying / Creating files -> DATA_MODIFICATION / LOW
    (
        r"\bCopy-Item\b|\bNew-Item\b|(?<![\w-])cp\b|(?<![\w-])ni\b|\bxcopy\b|\brobocopy\b",
        RiskCategory.DATA_MODIFICATION,
        RiskLevel.LOW,
        "Creating or copying files/directories",
    ),
    # Encoded commands / Nested shells / Dynamic evaluation -> PRIVILEGE_ESCALATION / HIGH
    (
        r"\bEncodedCommand\b|-enc\b|\bInvoke-Expression\b|\biex\b|\bpowershell(\.exe)?\s+-[cE]\b|\bcmd(\.exe)?\s+/c\b",
        RiskCategory.PRIVILEGE_ESCALATION,
        RiskLevel.HIGH,
        "Dynamic code evaluation or nested shell invocation",
    ),
]


class CommandSafetyClassifier:
    """Semantic and risk classifier for PowerShell commands."""

    def __init__(self) -> None:
        self.rules = [(re.compile(p, re.IGNORECASE), cat, level, reason) for p, cat, level, reason in RISK_RULES]

    def classify(self, command: str) -> tuple[RiskLevel, RiskCategory, str]:
        """Classify command into (RiskLevel, RiskCategory, explanation_reason)."""
        if not command or not command.strip():
            return RiskLevel.SAFE, RiskCategory.READ_ONLY, "Empty command"

        cmd_clean = command.strip()
        first_word = cmd_clean.split()[0].lower()

        # Check explicit destructive & risky rule patterns first
        for pattern, category, level, reason in self.rules:
            if pattern.search(cmd_clean):
                return level, category, reason

        # Check for command chaining (';' or '&&' or '||')
        if any(op in cmd_clean for op in (";", "&&", "||")):
            parts = re.split(r";|&&|\|\|", cmd_clean)
            highest_level = RiskLevel.SAFE
            highest_category = RiskCategory.READ_ONLY
            reasons = []
            for part in parts:
                if part.strip():
                    lvl, cat, rsn = self.classify(part.strip())
                    reasons.append(rsn)
                    if lvl == RiskLevel.CRITICAL or highest_level == RiskLevel.CRITICAL:
                        highest_level = RiskLevel.CRITICAL
                    elif lvl == RiskLevel.HIGH and highest_level != RiskLevel.CRITICAL:
                        highest_level = RiskLevel.HIGH
                    elif lvl == RiskLevel.MEDIUM and highest_level not in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                        highest_level = RiskLevel.MEDIUM
                    elif lvl == RiskLevel.LOW and highest_level == RiskLevel.SAFE:
                        highest_level = RiskLevel.LOW
                    if cat != RiskCategory.READ_ONLY:
                        highest_category = cat

            return highest_level, highest_category, "Chained execution: " + ", ".join(set(reasons))

        # Check read-only prefixes and explicit read-only commands
        if first_word in READ_ONLY_COMMANDS or any(first_word.startswith(p) for p in READ_ONLY_PREFIXES):
            return RiskLevel.SAFE, RiskCategory.READ_ONLY, "Read-only system inspection"

        # Check safe user launch actions (opening websites, settings, apps, locking workstation)
        if first_word in SAFE_LAUNCH_COMMANDS or "start-process" in first_word:
            return RiskLevel.LOW, RiskCategory.SAFE_ACTION, "Safe application or website launch"

        # Default fallback for unknown or generic commands
        return RiskLevel.LOW, RiskCategory.UNKNOWN, "Generic command execution"
