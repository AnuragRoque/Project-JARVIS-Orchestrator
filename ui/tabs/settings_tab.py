"""Tab 5 — Settings: global preferences + one auto-built section per module.

The global section covers cross-cutting prefs (permission mode, wake words,
theme, model, keys). Every module contributes its own section automatically from
its ``settings_schema()`` — a module needs **no edits here** to appear; a module
that returns a ``settings_widget()`` renders that custom widget instead. Secrets
(API keys) live in ``.env``; everything else in JSON namespaces.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jarvis.app.config.settings import ModuleSettings, get_settings
from jarvis.app.logsetup import get_logger

log = get_logger("settings.ui")


class SettingsTab(QWidget):
    def __init__(self, controller, modules=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctrl = controller
        self.modules = modules or []
        self.gs = get_settings()
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        self.col = QVBoxLayout(host)
        self.col.setContentsMargins(22, 18, 22, 18)
        self.col.setSpacing(16)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        self.saved = QLabel("")
        self.saved.setObjectName("Subtitle")
        self.saved.setAlignment(Qt.AlignmentFlag.AlignRight)
        outer.addWidget(self.saved)

        self._build_general()
        self._build_secrets()
        for m in self.modules:
            self._build_module_section(m)
        self.col.addStretch(1)

    def _flash_saved(self) -> None:
        self.saved.setText("Saved ✓")
        QTimer.singleShot(1400, lambda: self.saved.setText(""))

    def _group(self, title: str) -> QFormLayout:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.col.addWidget(box)
        return form

    # --------------------------------------------------------- general
    def _build_general(self) -> None:
        form = self._group("General")

        mode = QComboBox()
        mode.addItems(["Auto", "Partial", "Manual"])
        mode.setCurrentText(self.ctrl.permission_mode.capitalize())
        mode.currentTextChanged.connect(self._on_mode)
        form.addRow("Permission mode", mode)

        self.wake = QLineEdit(", ".join(self.gs.get("wake_words") or []))
        self.wake.setPlaceholderText("jarvis, friday, hey jarvis")
        self.wake.editingFinished.connect(self._on_wake)
        form.addRow("Wake words (comma-separated)", self.wake)

        req = QCheckBox("Ignore speech without a wake word (live mode)")
        req.setChecked(bool(self.gs.get("require_wake_word")))
        req.toggled.connect(lambda v: self._save_global("require_wake_word", bool(v)))
        form.addRow("", req)

        speak = QCheckBox("Speak replies aloud")
        speak.setChecked(bool(self.ctrl.cfg.get("speak_replies")))
        speak.toggled.connect(lambda v: self._save_cfg("speak_replies", bool(v)))
        form.addRow("", speak)

        barge = QCheckBox("Let me interrupt by speaking (barge-in)")
        barge.setChecked(bool(self.ctrl.cfg.get("barge_in")))
        barge.toggled.connect(lambda v: self._save_cfg("barge_in", bool(v)))
        form.addRow("", barge)

        cap = QSpinBox()
        cap.setRange(0, 5000)
        cap.setSingleStep(20)
        cap.setValue(int(self.ctrl.cfg.get("max_spoken_chars") or 0))
        cap.setToolTip("Trim spoken replies to this many characters (0 = no cap). "
                       "The full text still shows on screen.")
        cap.valueChanged.connect(lambda v: self._save_cfg("max_spoken_chars", int(v)))
        form.addRow("Spoken length cap", cap)

        model = QLineEdit(str(self.ctrl.cfg.get("openai_model") or ""))
        model.editingFinished.connect(
            lambda: self._save_cfg("openai_model", model.text().strip(),
                                   note="applies on restart"))
        form.addRow("Model", model)

        theme = QComboBox()
        theme.addItems(["dark", "light"])
        theme.setCurrentText(str(self.gs.get("theme") or "dark"))
        theme.currentTextChanged.connect(
            lambda v: self._save_global("theme", v, note="applies on restart"))
        form.addRow("Theme", theme)

        start_min = QCheckBox("Start minimised to the tray")
        start_min.setChecked(bool(self.gs.get("start_minimized")))
        start_min.toggled.connect(lambda v: self._save_global("start_minimized", bool(v)))
        form.addRow("", start_min)

        autostart = QCheckBox("Launch on Windows login")
        autostart.setChecked(bool(self.gs.get("autostart")))
        autostart.toggled.connect(self._on_autostart)
        form.addRow("", autostart)

    def _build_secrets(self) -> None:
        form = self._group("API keys (stored in .env)")
        cfg = self.ctrl.cfg

        self.k_openai = QLineEdit(cfg.openai_key)
        self.k_openai.setEchoMode(QLineEdit.EchoMode.Password)
        self.k_openai.setPlaceholderText("sk-…")
        self.k_openai.editingFinished.connect(self._on_keys)
        form.addRow("OpenAI API key", self.k_openai)

        self.k_sarvam = QLineEdit(cfg.sarvam_key)
        self.k_sarvam.setEchoMode(QLineEdit.EchoMode.Password)
        self.k_sarvam.editingFinished.connect(self._on_keys)
        form.addRow("Sarvam API key", self.k_sarvam)

        note = QLabel("Key changes take effect on restart.")
        note.setObjectName("Subtitle")
        form.addRow("", note)

    # --------------------------------------------------- per-module (auto)
    def _build_module_section(self, module) -> None:
        # A module may render a fully custom settings widget.
        custom = None
        try:
            custom = module.settings_widget()
        except Exception:
            custom = None
        if custom is not None:
            box = QGroupBox(getattr(module, "name", module.id))
            v = QVBoxLayout(box)
            v.addWidget(custom)
            self.col.addWidget(box)
            return

        try:
            schema = module.settings_schema()
        except Exception:
            schema = []
        if not schema:
            return

        store = ModuleSettings(module.id)
        form = self._group(getattr(module, "name", module.id))
        for field in schema:
            widget = self._field_widget(field, store)
            if widget is not None:
                form.addRow(field.label, widget)

    def _field_widget(self, field, store):
        key, default = field.key, field.default
        value = store.get(key, default)

        def save(v):
            store.set(key, v)
            self._flash_saved()

        if field.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(lambda v: save(bool(v)))
            return w
        if field.kind == "int":
            w = QSpinBox()
            w.setRange(-1_000_000, 1_000_000)
            w.setValue(int(value) if value is not None else 0)
            w.valueChanged.connect(lambda v: save(int(v)))
            return w
        if field.kind == "choice":
            w = QComboBox()
            w.addItems([str(c) for c in (field.choices or [])])
            if value is not None:
                w.setCurrentText(str(value))
            w.currentTextChanged.connect(save)
            return w
        # text / secret
        w = QLineEdit(str(value) if value is not None else "")
        if field.kind == "secret":
            w.setEchoMode(QLineEdit.EchoMode.Password)
        w.editingFinished.connect(lambda: save(w.text()))
        return w

    # ------------------------------------------------------------- saves
    def _save_global(self, key, value, note: str = "") -> None:
        self.gs.set(key, value)
        self._flash_saved()
        if note:
            self.saved.setText(f"Saved ✓ ({note})")

    def _save_cfg(self, key, value, note: str = "") -> None:
        try:
            self.ctrl.cfg.update({key: value})
        except Exception:
            log.debug("cfg save failed", exc_info=True)
        self._flash_saved()
        if note:
            self.saved.setText(f"Saved ✓ ({note})")

    def _on_mode(self, text: str) -> None:
        self.ctrl.set_permission_mode(text.lower())
        self._flash_saved()

    def _on_wake(self) -> None:
        words = [w.strip() for w in self.wake.text().split(",") if w.strip()]
        self._save_global("wake_words", words or ["jarvis"])

    def _on_autostart(self, on: bool) -> None:
        self._save_global("autostart", bool(on))
        try:
            from jarvis.app.autostart import set_autostart
            set_autostart(bool(on))
        except Exception:
            # Autostart wiring is Phase 8; persist the preference regardless.
            log.debug("autostart apply skipped", exc_info=True)

    def _on_keys(self) -> None:
        openai = self.k_openai.text().strip()
        sarvam = self.k_sarvam.text().strip()
        try:
            self.ctrl.cfg.set_keys(openai, sarvam)
            self.saved.setText("Saved ✓ (keys apply on restart)")
            QTimer.singleShot(1600, lambda: self.saved.setText(""))
        except Exception:
            log.debug("key save failed", exc_info=True)
