"""Qt stylesheets for dark and light modes."""

DARK = """
* { font-family: 'Segoe UI', 'Segoe UI Variable', sans-serif; }
QWidget { background: #16181d; color: #e6e8ee; font-size: 13px; }
QMainWindow, QDialog { background: #16181d; }

#Sidebar {
    background: #1c1f26;
    border-right: 1px solid #262a33;
}
#Sidebar QListWidget { background: transparent; border: none; outline: none; }
#Sidebar QListWidget::item {
    padding: 9px 16px; margin: 1px 6px; border-radius: 8px; color: #aab0bd;
}
#Sidebar QListWidget::item:selected { background: #2b62ff; color: white; }
#Sidebar QListWidget::item:hover:!selected { background: #262a33; }

#Brand { font-size: 15px; font-weight: 600; color: #ffffff; padding: 16px 18px 8px 18px; }
#BrandSub { color: #6b7280; padding: 0 18px 12px 18px; font-size: 11px; }

QLineEdit {
    background: #1c1f26; border: 1px solid #2b303b; border-radius: 10px;
    padding: 10px 14px; font-size: 14px; selection-background-color: #2b62ff;
}
QLineEdit:focus { border: 1px solid #2b62ff; }

QListWidget#Results { background: #16181d; border: none; outline: none; }
QListWidget#Results::item {
    background: #1c1f26; border: 1px solid #23272f; border-radius: 10px;
    margin: 4px 8px; padding: 0px;
}
QListWidget#Results::item:selected { border: 1px solid #2b62ff; background: #1f2530; }
QListWidget#Results::item:hover { border: 1px solid #34506b; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #333844; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #454b59; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }

QPushButton {
    background: #262a33; border: 1px solid #2f343f; border-radius: 8px;
    padding: 7px 14px; color: #e6e8ee;
}
QPushButton:hover { background: #2f343f; }
QPushButton:pressed { background: #21252d; }
QPushButton#Primary { background: #2b62ff; border: none; color: white; }
QPushButton#Primary:hover { background: #3d70ff; }
QPushButton#Danger { background: #7f1d1d; border: none; color: #fee2e2; }
QPushButton#Danger:hover { background: #991b1b; }

QLabel#Header { font-size: 20px; font-weight: 600; padding: 4px 2px; }
QLabel#Sub { color: #8b93a3; }
QLabel.pill {
    background: #23272f; border-radius: 6px; padding: 2px 8px; color: #9aa2b1;
}
QStatusBar { background: #1c1f26; color: #8b93a3; border-top: 1px solid #262a33; }
QCheckBox { spacing: 8px; }
QSpinBox, QComboBox, QDoubleSpinBox {
    background: #1c1f26; border: 1px solid #2b303b; border-radius: 6px; padding: 4px 8px;
}
QPlainTextEdit, QTextEdit {
    background: #1c1f26; border: 1px solid #2b303b; border-radius: 8px;
}
"""

LIGHT = """
QWidget { background: #f6f7f9; color: #1a1d22; font-family: 'Segoe UI'; font-size: 13px; }
#Sidebar { background: #eceef2; border-right: 1px solid #dcdfe5; }
#Sidebar QListWidget::item { padding: 9px 16px; margin: 1px 6px; border-radius: 8px; color: #3d4350; }
#Sidebar QListWidget::item:selected { background: #2b62ff; color: white; }
QLineEdit { background: white; border: 1px solid #d3d7de; border-radius: 10px; padding: 10px 14px; font-size: 14px; }
QListWidget#Results::item { background: white; border: 1px solid #e2e5ea; border-radius: 10px; margin: 4px 8px; }
QPushButton#Primary { background: #2b62ff; color: white; border: none; border-radius: 8px; padding: 7px 14px; }
"""


def stylesheet(dark: bool) -> str:
    return DARK if dark else LIGHT
