"""Two-layer theming for the whole app.

**Layer 1 — the global theme.** A named :class:`Palette` (blue / dark / light /
red / …) chosen in Settings that colours the whole app: backgrounds, panels,
text, and the default accent. :data:`theme_manager` holds the current one,
persists it, and emits :pyattr:`ThemeManager.changed` so every surface can
re-apply its stylesheet live.

**Layer 2 — the permission accent (the "robot mood").** The floating window
overrides its accent from the current permission mode, like the robots in the
movies: **blue = controlled/safe (Manual)**, **amber = supervised (Partial)**,
**red = unrestrained (Auto)**. This is a safety signal, so it wins over the
global theme's accent *for the orb surface only*.

Stylesheets are built with :class:`string.Template` (``$name``) so literal CSS
braces need no escaping.
"""
from __future__ import annotations

from dataclasses import dataclass
from string import Template

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap


# --------------------------------------------------------------------- palette
@dataclass(frozen=True)
class Palette:
    key: str
    label: str
    dark: bool
    bg: str        # window background
    panel: str     # panels / cards / tabs
    text: str      # primary text
    subtext: str   # muted text
    accent: str    # primary accent
    accent2: str   # darker accent (gradient partner)


THEMES: dict[str, Palette] = {
    "blue":       Palette("blue", "Blue", True,
                          "#0d0f13", "#16191f", "#f2f4f8", "#8a93a3", "#2f9bff", "#0e63ff"),
    "dark":       Palette("dark", "Dark", True,
                          "#0e0f11", "#17181c", "#eceef2", "#8a8f99", "#9aa4b2", "#5b6270"),
    "dark black": Palette("dark black", "Dark Black", True,
                          "#050506", "#101013", "#e9eaee", "#7e828b", "#3b82f6", "#1e40af"),
    "dark blue":  Palette("dark blue", "Dark Blue", True,
                          "#0a0f1e", "#111a30", "#eaf0fb", "#8090a8", "#4c8dff", "#1b4fd6"),
    "red":        Palette("red", "Red", True,
                          "#120c0e", "#1e1416", "#f6eef0", "#b48a90", "#ff4d5e", "#c81e2e"),
    "light":      Palette("light", "Light", False,
                          "#f4f6fa", "#ffffff", "#1b2027", "#5c6473", "#2f7bff", "#1560e6"),
    "light blue": Palette("light blue", "Light Blue", False,
                          "#eaf1fc", "#ffffff", "#12233d", "#557092", "#2b7fff", "#0e63ff"),
}

DEFAULT_THEME = "blue"


# --------------------------------------------------- permission "robot mood"
# (accent, accent2) per Auto / Partial / Manual — the floating-window override.
PERMISSION_ACCENTS: dict[str, tuple[str, str]] = {
    "manual":  ("#2f9bff", "#0e63ff"),   # blue  — controlled, asks first (good AI)
    "partial": ("#ffa63d", "#ff7a1a"),   # amber — supervised, middle ground
    "auto":    ("#ff4d5e", "#c81e2e"),   # red   — unrestrained (the movie villain)
}


def permission_accent(mode: str) -> tuple[str, str]:
    return PERMISSION_ACCENTS.get((mode or "").lower(), PERMISSION_ACCENTS["partial"])


# ---------------------------------------------------------------- colour utils
def _rgb(hex_color: str) -> str:
    c = QColor(hex_color)
    return f"{c.red()}, {c.green()}, {c.blue()}"


def _rgba(hex_color: str, alpha: float) -> str:
    return f"rgba({_rgb(hex_color)}, {alpha})"


def dot_pixmap(color: str, size: int = 12) -> QPixmap:
    """A filled circle — used as the per-mode dot on the permission selector."""
    oversample = 3
    px = size * oversample
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    inset = oversample
    p.drawEllipse(inset, inset, px - 2 * inset, px - 2 * inset)
    p.end()
    pm.setDevicePixelRatio(oversample)
    return pm


# ------------------------------------------------------------ shared QSS vars
def _vars(pal: Palette, accent: str | None, accent2: str | None) -> dict:
    a = accent or pal.accent
    a2 = accent2 or pal.accent2
    if pal.dark:
        surface, surface_hi = _rgba("#ffffff", 0.05), _rgba("#ffffff", 0.14)
        border, border_hi = _rgba("#ffffff", 0.10), _rgba("#ffffff", 0.18)
        bub_ass, bub_ass_bd = _rgba("#ffffff", 0.07), _rgba("#ffffff", 0.09)
        step_bg, step_detail_bg = _rgba("#ffffff", 0.045), _rgba("#000000", 0.30)
        card_top, card_bot = _rgba(pal.panel, 0.92), _rgba(pal.bg, 0.95)
    else:
        surface, surface_hi = _rgba("#000000", 0.04), _rgba("#000000", 0.10)
        border, border_hi = _rgba("#000000", 0.10), _rgba("#000000", 0.16)
        bub_ass, bub_ass_bd = _rgba("#000000", 0.05), _rgba("#000000", 0.08)
        step_bg, step_detail_bg = _rgba("#000000", 0.04), _rgba("#000000", 0.06)
        card_top, card_bot = _rgba("#ffffff", 0.97), _rgba(pal.panel, 0.99)
    return {
        "bg": pal.bg, "panel": pal.panel, "text": pal.text, "sub": pal.subtext,
        "accent": a, "accent2": a2,
        "accent_soft": _rgba(a, 0.16), "accent_bd": _rgba(a, 0.38),
        "surface": surface, "surface_hi": surface_hi,
        "border": border, "border_hi": border_hi,
        "bub_ass": bub_ass, "bub_ass_bd": bub_ass_bd,
        "step_bg": step_bg, "step_detail_bg": step_detail_bg,
        "card_top": card_top, "card_bot": card_bot,
        "tab_hover": _rgba(pal.text, 0.08),
    }


# ---------------------------------------------------------------- glass (orb)
_GLASS = Template("""
* { font-family: 'Segoe UI', 'Inter', sans-serif; color: $text; }

#Card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $card_top, stop:1 $card_bot);
    border: 1px solid $border;
    border-radius: 22px;
}

#OrbMark { color: #ffffff; font-size: 30px; font-weight: 800; }

#Title { font-size: 15px; font-weight: 700; letter-spacing: 2px; color: $text; }
#Subtitle { font-size: 11px; color: $sub; letter-spacing: 1px; }

#WinBtn {
    background: transparent; border: none; border-radius: 8px;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
}
#WinBtn:hover { background: $surface_hi; }
#WinBtn:pressed { background: $surface; }

QScrollArea, #Chat { background: transparent; border: none; }

/* Full-width conversation rows (compact quick-bar): a small role caption over
   a word-wrapped body; user rows carry the accent, JARVIS rows a faint panel. */
#MsgUser {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent2, stop:1 $accent);
    border: none; border-radius: 13px;
}
#MsgAssistant {
    background: $bub_ass; border: 1px solid $bub_ass_bd; border-radius: 13px;
}
#MsgRole { color: $sub; font-size: 9px; font-weight: 800; letter-spacing: 1px; }
#MsgBody { color: $text; font-size: 12px; }
#MsgRoleUser { color: rgba(255,255,255,0.75); font-size: 9px; font-weight: 800; letter-spacing: 1px; }
#MsgBodyUser { color: #ffffff; font-size: 12px; font-weight: 600; }
#ActivityText { color: $sub; font-size: 11px; }

#Bubble_user, #Bubble_assistant, #Bubble_system {
    border-radius: 14px; padding: 10px 13px; font-size: 13px;
}
#Bubble_user {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent2, stop:1 $accent);
    color: #ffffff; font-weight: 600;
}
#Bubble_assistant {
    background: $bub_ass; border: 1px solid $bub_ass_bd; color: $text;
}
#Bubble_system { background: transparent; color: $sub; font-size: 11px; }

#Status { color: $sub; font-size: 11px; }

#StepHeader {
    background: $step_bg; border: 1px solid $bub_ass_bd;
    border-radius: 10px; padding: 5px 11px; color: $accent;
    font-size: 11px; font-weight: 600; text-align: left;
}
#StepHeader:hover { background: $accent_soft; color: $text; }
#StepDetail {
    background: $step_detail_bg; border: 1px solid $bub_ass_bd;
    border-radius: 9px; padding: 8px 11px; color: $text;
    font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px;
}

#Mic {
    border-radius: 34px;
    min-width: 68px; max-width: 68px; min-height: 68px; max-height: 68px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $accent, stop:1 $accent2);
    color: #ffffff; border: 1px solid $border_hi;
}
#Mic:hover { background: $accent; }
#Mic[recording="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5d6c, stop:1 #d21f3c);
}

#MicMini {
    border-radius: 17px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
    background: transparent; color: $accent; border: none;
}
#MicMini:hover { background: $surface_hi; border-radius: 17px; }
#MicMini[recording="true"] { background: #d21f3c; }

#Ghost {
    background: $surface; border: 1px solid $border;
    border-radius: 21px; padding: 7px 14px; font-size: 12px; color: $text;
}
#Ghost:hover { background: $accent_soft; }

#Send {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $accent, stop:1 $accent2);
    border: none; border-radius: 21px;
    min-width: 42px; max-width: 42px; min-height: 42px; max-height: 42px;
}
#Send:hover { background: $accent; }

#InputWrap {
    background: $surface; border: 1px solid $border; border-radius: 22px;
}
#InputWrap[focused="true"] { border: 1px solid $accent; }
#Input {
    background: transparent; border: none; padding: 9px 6px 9px 16px;
    font-size: 13px; color: $text;
}

#LiveToggle {
    background: $surface; border: 1px solid $border; border-radius: 14px;
    padding: 5px 12px; color: $text; font-size: 11px; font-weight: 600;
}
#LiveToggle:hover { border: 1px solid $accent; }
#LiveToggle[live="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $accent, stop:1 $accent2);
    color: #ffffff; border: none;
}

#ModeCombo {
    background: $surface; border: 1px solid $border; border-radius: 12px;
    padding: 3px 10px; color: $text; font-size: 11px; font-weight: 600;
    min-height: 22px;
}
#ModeCombo:hover { border: 1px solid $accent; }
#ModeCombo::drop-down { border: none; width: 18px; }
#ModeCombo QAbstractItemView {
    background: $panel; border: 1px solid $border;
    selection-background-color: $accent_soft; color: $text; outline: none;
    border-radius: 8px; padding: 4px;
}

QScrollBar:vertical { background: transparent; width: 8px; margin: 4px; }
QScrollBar::handle:vertical { background: $surface_hi; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }

QSizeGrip { background: transparent; width: 14px; height: 14px; }
""")


# ---------------------------------------------------------------- app chrome
_APP = Template("""
QMainWindow, #AppRoot { background: $bg; }
QTabWidget::pane { border: none; background: $bg; }
QTabBar { background: $bg; }
QTabBar::tab {
    background: $panel; color: $sub;
    padding: 9px 18px; margin: 6px 3px 0 3px;
    border-top-left-radius: 9px; border-top-right-radius: 9px;
    font-size: 12px; font-weight: 600;
}
QTabBar::tab:selected { background: $accent2; color: #ffffff; }
QTabBar::tab:hover:!selected { background: $tab_hover; color: $text; }
QTabBar::tab:disabled { color: $sub; }

QGroupBox {
    border: 1px solid $border; border-radius: 12px;
    margin-top: 14px; padding: 12px; color: $text; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: $accent; }
QLabel { color: $text; }
QCheckBox { color: $text; }
QLineEdit, QComboBox, QSpinBox {
    background: $surface; border: 1px solid $border; border-radius: 8px;
    padding: 6px 9px; color: $text;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid $accent; }
QComboBox QAbstractItemView {
    background: $panel; color: $text; selection-background-color: $accent_soft;
    border: 1px solid $border;
}
""")


# ----------------------------------------------------------------- placeholder
_PLACEHOLDER = Template("""
#Placeholder { background: $bg; }
#PlaceholderTitle { font-size: 20px; font-weight: 700; color: $text; }
#PlaceholderBody { font-size: 13px; color: $sub; }
#PlaceholderBadge {
    background: $accent_soft; color: $accent; border: 1px solid $accent_bd;
    border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 700;
}
""")


# ------------------------------------------------------------------- toast
_TOAST = Template("""
#ToastCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $card_top, stop:1 $card_bot);
    border: 1px solid $accent; border-radius: 16px;
}
#ToastTitle { color: $accent; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
#ToastText { color: $text; font-size: 15px; font-weight: 600; }
#ToastBtn {
    background: $surface; border: 1px solid $border;
    border-radius: 10px; padding: 6px 14px; color: $text; font-size: 12px;
}
#ToastBtn:hover { background: $accent_soft; }
#ToastPrimary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent2, stop:1 $accent);
    border: none; border-radius: 10px; padding: 6px 14px; color: #fff;
    font-size: 12px; font-weight: 700;
}
""")


# ------------------------------------------------------------------ terminal
# Consoles read best dark; keep the dark console but tint accents from the theme.
_TERMINAL = Template("""
QWidget { background-color: #1e1e2e; color: #e0e0e0; }
#panelFrame { background-color: #252537; border: 1px solid #333349; border-radius: 8px; }
#panelHeader { color: #9aa0b5; font-weight: 700; letter-spacing: 1px; font-size: 11px; padding: 2px 0; }
#terminalOutput {
    background-color: #0c0c0c; border: 1px solid #2c2c3f; border-radius: 6px;
    padding: 6px 8px; color: #d4d4d4;
}
#terminalPrompt { color: #5ef19a; font-weight: 700; padding-left: 2px; }
#terminalInput {
    background-color: #0c0c0c; border: 1px solid #2c2c3f; border-radius: 6px;
    padding: 6px 8px; color: #d4d4d4;
}
#terminalInput:focus { border: 1px solid #5ef19a; }
QLineEdit, QComboBox {
    background-color: #16161f; border: 1px solid #2c2c3f; border-radius: 6px;
    padding: 5px 8px; color: #e0e0e0;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QPushButton {
    background-color: #3a3a5a; border: none; border-radius: 6px;
    padding: 6px 16px; color: #e0e0e0; font-weight: 600;
}
QPushButton:hover { background-color: $accent2; }
QPushButton:pressed { background-color: #33334f; }
#miniButton { padding: 3px 10px; font-size: 11px; }
#statusLabel { color: #e0b341; font-weight: 600; font-size: 11px; }
""")


# ---------------------------------------------------------- builder functions
def glass_qss(pal: Palette, accent: str | None = None, accent2: str | None = None) -> str:
    return _GLASS.substitute(_vars(pal, accent, accent2))


def app_qss(pal: Palette) -> str:
    return _APP.substitute(_vars(pal, None, None))


def placeholder_qss(pal: Palette) -> str:
    return _PLACEHOLDER.substitute(_vars(pal, None, None))


def toast_qss(pal: Palette, accent: str | None = None, accent2: str | None = None) -> str:
    return _TOAST.substitute(_vars(pal, accent, accent2))


def terminal_qss(pal: Palette) -> str:
    return _TERMINAL.substitute(_vars(pal, None, None))


# --------------------------------------------------------------- manager
class ThemeManager(QObject):
    """Holds the current global theme and notifies surfaces when it changes."""

    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._key: str | None = None

    def current_key(self) -> str:
        if self._key is None:
            self._key = self._load_key()
        return self._key

    def palette(self) -> Palette:
        return THEMES.get(self.current_key(), THEMES[DEFAULT_THEME])

    def set_theme(self, key: str) -> None:
        key = (key or "").lower()
        if key not in THEMES or key == self.current_key():
            if key not in THEMES:
                return
        self._key = key
        try:
            from jarvis.app.config.settings import get_settings
            get_settings().set("theme", key)
        except Exception:
            pass
        self.changed.emit()

    @staticmethod
    def _load_key() -> str:
        try:
            from jarvis.app.config.settings import get_settings
            raw = str(get_settings().get("theme") or DEFAULT_THEME).lower()
            return raw if raw in THEMES else DEFAULT_THEME
        except Exception:
            return DEFAULT_THEME


theme_manager = ThemeManager()
