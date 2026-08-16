"""App-wide palette and scoped Qt stylesheets.

Each surface keeps its own look by setting one of these on its subtree:
- ``VOICE_STYLE``    — the monochrome glass used by the orb + Voice Chat tab
- ``TERMINAL_STYLE`` — the dual-pane terminal look
- ``APP_STYLE``      — base chrome for the tabbed main window

The timeline tab uses its module's own stylesheet
(``jarvis.modules.timeline.recall.ui.theme.stylesheet``).
"""

ACCENT = "#2f9bff"
ACCENT_2 = "#0e63ff"
BG = "#0d0f13"
PANEL = "#16191f"


# --------------------------------------------------------------- glass (voice)
VOICE_STYLE = f"""
* {{
    font-family: 'Segoe UI', 'Inter', sans-serif;
    color: #f2f4f8;
}}

#Card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(24,27,33,0.90), stop:1 rgba(13,15,19,0.94));
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 22px;
}}

#Orb {{
    background: qradialgradient(cx:0.5, cy:0.38, radius:0.95, fx:0.5, fy:0.35,
        stop:0 #64b6ff, stop:1 {ACCENT_2});
    border: 1px solid rgba(255,255,255,0.28);
    border-radius: 34px;
}}
#OrbMark {{ color: #ffffff; font-size: 30px; font-weight: 800; }}

#Title {{ font-size: 15px; font-weight: 700; letter-spacing: 2px; color: #ffffff; }}
#Subtitle {{ font-size: 11px; color: #8a93a3; letter-spacing: 1px; }}

#WinBtn {{
    background: rgba(255,255,255,0.05);
    border: none; border-radius: 6px; font-size: 14px; color: #aab2c0;
    min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
}}
#WinBtn:hover {{ background: rgba(255,255,255,0.14); color: #fff; }}

QScrollArea, #Chat {{ background: transparent; border: none; }}

#Bubble_user, #Bubble_assistant, #Bubble_system {{
    border-radius: 14px; padding: 10px 13px; font-size: 13px;
}}
#Bubble_user {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {ACCENT_2}, stop:1 {ACCENT});
    color: #ffffff; font-weight: 600;
}}
#Bubble_assistant {{
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.09); color: #e9edf3;
}}
#Bubble_system {{ background: transparent; color: #7b8494; font-size: 11px; }}

#Status {{ color: #8a93a3; font-size: 11px; }}

#Mic {{
    border-radius: 34px;
    min-width: 68px; max-width: 68px; min-height: 68px; max-height: 68px;
    font-size: 26px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    color: #ffffff; border: 1px solid rgba(255,255,255,0.18);
}}
#Mic:hover {{ background: {ACCENT}; }}
#Mic[recording="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5d6c, stop:1 #d21f3c);
}}

#MicMini {{
    border-radius: 19px;
    min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px;
    font-size: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    color: #ffffff; border: none;
}}
#MicMini:hover {{ background: {ACCENT}; }}
#MicMini[recording="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff5d6c, stop:1 #d21f3c);
}}

#Ghost {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 16px; padding: 7px 14px; font-size: 12px; color: #e9edf3;
}}
#Ghost:hover {{ background: rgba(47,155,255,0.18); }}

#Input {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 19px; padding: 8px 14px; font-size: 13px;
}}
#Input:focus {{ border: 1px solid {ACCENT}; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.16); border-radius: 4px; min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


# ----------------------------------------------------------------- terminal
TERMINAL_STYLE = """
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
QLineEdit:focus, QComboBox:focus { border: 1px solid #4fc3f7; }
QPushButton {
    background-color: #3a3a5a; border: none; border-radius: 6px;
    padding: 6px 16px; color: #e0e0e0; font-weight: 600;
}
QPushButton:hover { background-color: #4a4a70; }
QPushButton:pressed { background-color: #33334f; }
#miniButton { padding: 3px 10px; font-size: 11px; }
#statusLabel { color: #e0b341; font-weight: 600; font-size: 11px; }
"""


# ---------------------------------------------------------------- app chrome
APP_STYLE = f"""
QMainWindow, #AppRoot {{ background: {BG}; }}
QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar {{ background: {BG}; }}
QTabBar::tab {{
    background: {PANEL};
    color: #9aa2b1;
    padding: 9px 18px;
    margin: 6px 3px 0 3px;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    font-size: 12px; font-weight: 600;
}}
QTabBar::tab:selected {{ background: {ACCENT_2}; color: #ffffff; }}
QTabBar::tab:hover:!selected {{ background: #20242c; color: #d6dae2; }}
QTabBar::tab:disabled {{ color: #4b515c; }}
"""


# placeholder pages (Logs / Settings / Dashboard until their phases land)
PLACEHOLDER_STYLE = f"""
#Placeholder {{ background: {BG}; }}
#PlaceholderTitle {{ font-size: 20px; font-weight: 700; color: #e9edf3; }}
#PlaceholderBody {{ font-size: 13px; color: #8a93a3; }}
#PlaceholderBadge {{
    background: rgba(47,155,255,0.16); color: {ACCENT};
    border: 1px solid rgba(47,155,255,0.35);
    border-radius: 12px; padding: 4px 12px; font-size: 11px; font-weight: 700;
}}
"""
