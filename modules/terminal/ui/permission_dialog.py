from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.modules.terminal.core.models import RiskCategory, RiskLevel

RISK_COLORS = {
    RiskLevel.SAFE: "#5ef19a",
    RiskLevel.LOW: "#4fc3f7",
    RiskLevel.MEDIUM: "#e0b341",
    RiskLevel.HIGH: "#ff9800",
    RiskLevel.CRITICAL: "#e0574b",
}


class PermissionDialog(QDialog):
    """Modern reusable modal dialog asking user permission to execute risky commands."""

    def __init__(
        self,
        command: str,
        reason: str,
        risk_level: RiskLevel,
        category: RiskCategory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Jarvis Permission Request")
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #e0e0e0; }
            QLabel { color: #e0e0e0; font-size: 13px; }
            QPlainTextEdit {
                background-color: #0c0c0c;
                border: 1px solid #333349;
                border-radius: 6px;
                color: #5ef19a;
                font-family: "Cascadia Mono", Consolas, monospace;
                font-size: 12px;
                padding: 6px;
            }
            QPushButton {
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: 600;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header Title
        title_label = QLabel("⚠️  <b>Jarvis Requires Permission</b>")
        title_label.setStyleSheet("font-size: 15px; color: #ffffff;")
        layout.addWidget(title_label)

        # Action Explanation & Risk Badge Row
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        reason_label = QLabel(f"<b>Action:</b> {reason}")
        info_row.addWidget(reason_label, stretch=1)

        badge_color = RISK_COLORS.get(risk_level, "#e0b341")
        risk_badge = QLabel(f" {risk_level.value} RISK ")
        risk_badge.setStyleSheet(
            f"background-color: {badge_color}; color: #000000; "
            f"font-weight: 700; border-radius: 4px; padding: 2px 6px; font-size: 11px;"
        )
        info_row.addWidget(risk_badge)
        layout.addLayout(info_row)

        # Category
        cat_label = QLabel(f"<b>Category:</b> <span style='color:#9aa0b5;'>{category.value}</span>")
        layout.addWidget(cat_label)

        # Command Text Box
        cmd_header = QLabel("<b>Command to execute:</b>")
        layout.addWidget(cmd_header)

        cmd_box = QPlainTextEdit()
        cmd_box.setPlainText(command)
        cmd_box.setReadOnly(True)
        cmd_box.setMaximumHeight(100)
        layout.addWidget(cmd_box)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        deny_btn = QPushButton("Don't Allow")
        deny_btn.setStyleSheet("background-color: #5a2a2a; color: #ffffff;")
        deny_btn.clicked.connect(self.reject)
        btn_row.addWidget(deny_btn)

        allow_btn = QPushButton("Allow")
        allow_btn.setStyleSheet("background-color: #2e7d32; color: #ffffff;")
        allow_btn.setDefault(True)
        allow_btn.clicked.connect(self.accept)
        btn_row.addWidget(allow_btn)

        layout.addLayout(btn_row)

    @classmethod
    def request_approval(
        cls,
        command: str,
        reason: str,
        risk_level: RiskLevel,
        category: RiskCategory,
        parent: QWidget | None = None,
    ) -> bool:
        dialog = cls(command, reason, risk_level, category, parent)
        return dialog.exec() == QDialog.DialogCode.Accepted
