"""Rendering of a single activity result row."""
from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_KIND_META = {
    "session": ("🖥️", "#2b62ff"),
    "browser": ("🌐", "#22c55e"),
    "file": ("📄", "#f59e0b"),
    "resource": ("📁", "#a855f7"),
}


def _local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def format_time(dt: datetime | None) -> str:
    dt = _local(dt)
    if dt is None:
        return ""
    now = datetime.now().astimezone()
    if dt.date() == now.date():
        return dt.strftime("%I:%M %p").lstrip("0")
    if (now.date() - dt.date()).days == 1:
        return "Yesterday " + dt.strftime("%I:%M %p").lstrip("0")
    return dt.strftime("%b %d, %I:%M %p")


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def make_result_widget(result: dict) -> QWidget:
    kind = result.get("kind", "session")
    icon, color = _KIND_META.get(kind, ("•", "#888"))

    root = QFrame()
    root.setObjectName("ResultRow")
    outer = QHBoxLayout(root)
    outer.setContentsMargins(14, 10, 14, 10)
    outer.setSpacing(12)

    icon_lbl = QLabel(icon)
    icon_lbl.setFixedWidth(24)
    icon_lbl.setStyleSheet("font-size: 18px;")
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
    outer.addWidget(icon_lbl)

    col = QVBoxLayout()
    col.setSpacing(2)

    title = result.get("title") or "(untitled)"
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #e6e8ee;")
    title_lbl.setWordWrap(False)
    # Let long titles shrink instead of forcing a huge minimum width on the whole
    # list (and, through it, the app window).
    title_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    col.addWidget(title_lbl)

    # Subtitle: app/domain/path
    if kind == "browser":
        sub = result.get("domain") or result.get("url", "")
    elif kind == "file":
        sub = result.get("path", "")
    else:
        sub = result.get("app", "")
    sub_lbl = QLabel(sub)
    sub_lbl.setStyleSheet("color: #8b93a3; font-size: 12px;")
    sub_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    col.addWidget(sub_lbl)
    outer.addLayout(col, 1)

    # Right column: time + duration + kind badge
    right = QVBoxLayout()
    right.setSpacing(3)
    right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    time_lbl = QLabel(format_time(result.get("start_time")))
    time_lbl.setStyleSheet("color: #aab0bd; font-size: 12px;")
    time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
    right.addWidget(time_lbl)

    meta_bits = []
    dur = format_duration(result.get("duration_seconds"))
    if dur:
        meta_bits.append(dur)
    app_name = result.get("app") or result.get("browser") or ""
    badge = QLabel(f"{app_name}  {dur}".strip())
    badge.setStyleSheet(f"color: {color}; font-size: 11px;")
    badge.setAlignment(Qt.AlignmentFlag.AlignRight)
    right.addWidget(badge)
    outer.addLayout(right)

    return root
