"""Settings / privacy control page."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget, QPlainTextEdit,
)

from ..config import get_config, update_config


class SettingsPage(QWidget):
    changed = Signal()          # tracking-related toggles changed
    clear_requested = Signal()  # user asked to clear all history

    def __init__(self):
        super().__init__()
        cfg = get_config()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QLabel("Settings & Privacy")
        header.setObjectName("Header")
        root.addWidget(header)
        root.addWidget(_sub("All data stays on this device. Nothing is uploaded."))

        # --- Tracking toggles ---
        root.addWidget(_section("Tracking"))
        self.cb_tracking = QCheckBox("Enable activity tracking")
        self.cb_tracking.setChecked(cfg.tracking_enabled)
        self.cb_browser = QCheckBox("Enable browser tracking (extension API)")
        self.cb_browser.setChecked(cfg.browser_tracking_enabled)
        self.cb_private = QCheckBox("Private mode (record nothing while on)")
        self.cb_private.setChecked(cfg.private_mode)
        self.cb_semantic = QCheckBox("Enable semantic indexing (optional, local)")
        self.cb_semantic.setChecked(cfg.semantic_indexing_enabled)
        for cb in (self.cb_tracking, self.cb_browser, self.cb_private,
                   self.cb_semantic):
            root.addWidget(cb)
            cb.toggled.connect(self._on_toggle)

        # --- Capture tuning ---
        root.addWidget(_section("Capture"))
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        self.sp_poll = QDoubleSpinBox()
        self.sp_poll.setRange(0.5, 30.0)
        self.sp_poll.setSingleStep(0.5)
        self.sp_poll.setValue(cfg.poll_interval_seconds)
        self.sp_idle = QSpinBox()
        self.sp_idle.setRange(0, 3600)
        self.sp_idle.setValue(int(cfg.idle_timeout_seconds))
        self.sp_retention = QSpinBox()
        self.sp_retention.setRange(0, 3650)
        self.sp_retention.setValue(cfg.retention_days)
        form.addRow("Poll interval (s)", self.sp_poll)
        form.addRow("Idle timeout (s, 0=off)", self.sp_idle)
        form.addRow("Retention days (0=forever)", self.sp_retention)
        root.addLayout(form)

        # --- Exclusions ---
        root.addWidget(_section("Exclusions"))
        root.addWidget(_sub("One entry per line."))
        excl_row = QHBoxLayout()
        pcol = QVBoxLayout()
        pcol.addWidget(QLabel("Excluded processes (e.g. KeePass.exe)"))
        self.txt_proc = QPlainTextEdit("\n".join(cfg.excluded_processes))
        self.txt_proc.setFixedHeight(90)
        pcol.addWidget(self.txt_proc)
        dcol = QVBoxLayout()
        dcol.addWidget(QLabel("Excluded domains (e.g. mybank.com)"))
        self.txt_dom = QPlainTextEdit("\n".join(cfg.excluded_domains))
        self.txt_dom.setFixedHeight(90)
        dcol.addWidget(self.txt_dom)
        excl_row.addLayout(pcol)
        excl_row.addLayout(dcol)
        root.addLayout(excl_row)

        # --- Browser pairing ---
        root.addWidget(_section("Browser"))
        root.addWidget(_sub(
            "Load the extension in extension/ and paste this token into its "
            "options to pair. The API listens on 127.0.0.1."))
        pair_row = QHBoxLayout()
        self.token_field = QLineEdit(self._read_token())
        self.token_field.setReadOnly(True)
        btn_copy = QPushButton("Copy token")
        btn_copy.clicked.connect(self._copy_token)
        pair_row.addWidget(self.token_field, 1)
        pair_row.addWidget(btn_copy)
        root.addLayout(pair_row)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("Primary")
        self.btn_save.clicked.connect(self._save)
        self.btn_clear = QPushButton("Clear All History")
        self.btn_clear.setObjectName("Danger")
        self.btn_clear.clicked.connect(self.clear_requested.emit)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_clear)
        root.addLayout(btn_row)
        root.addStretch(1)

    def _read_token(self) -> str:
        try:
            from ..api import get_api_token
            return get_api_token()
        except Exception:
            return "(start the app to generate a token)"

    def _copy_token(self) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.token_field.text())

    def _on_toggle(self, _checked: bool) -> None:
        update_config(
            tracking_enabled=self.cb_tracking.isChecked(),
            browser_tracking_enabled=self.cb_browser.isChecked(),
            private_mode=self.cb_private.isChecked(),
            semantic_indexing_enabled=self.cb_semantic.isChecked(),
        )
        self.changed.emit()

    def _save(self) -> None:
        procs = [l.strip() for l in self.txt_proc.toPlainText().splitlines()
                 if l.strip()]
        doms = [l.strip() for l in self.txt_dom.toPlainText().splitlines()
                if l.strip()]
        update_config(
            poll_interval_seconds=self.sp_poll.value(),
            idle_timeout_seconds=float(self.sp_idle.value()),
            retention_days=self.sp_retention.value(),
            excluded_processes=procs,
            excluded_domains=doms,
        )
        self.changed.emit()
        self.btn_save.setText("Saved ✓")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self.btn_save.setText("Save Settings"))


def _section(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
    return lbl


def _sub(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Sub")
    return lbl
