# ANALYSIS — What exists, what we keep, what we drop

This is the honest inventory. For every existing piece: what it does, how mature
it is, and its fate in the merge (**KEEP AS-IS / PORT / REUSE LOGIC / ARCHIVE**).

---

## 1. `jarvis_voice_core/` — the floating voice window  → **KEEP (becomes the hub UI)**

**Stack:** PyQt6 · Sarvam STT · Windows SAPI TTS (pywin32) · OpenAI streaming chat.

**What's good and stays:**
- [`ui/floating_window.py`](jarvis_voice_core/ui/floating_window.py) — frameless,
  draggable, always-on-top glass card; collapse-to-orb; live hands-free mode with
  VAD; sentence-by-sentence TTS flushing. This becomes the **floating orb** shell.
- [`core/stt.py`](jarvis_voice_core/core/stt.py) — `Recorder` + `LiveListener`
  (VAD, silence cut-off). Voice input for the whole app.
- [`core/tts.py`](jarvis_voice_core/core/tts.py) — `SpeechQueue`, background
  speaking. Voice output for the whole app.
- [`core/chat.py`](jarvis_voice_core/core/chat.py) — OpenAI streaming with a reused
  client. Good for **plain** replies; the tool-calling path comes from the terminal module.
- Wake-word gating in `_apply_wake_word()` — the seed for the multi-wake-word feature.

**What changes:**
- The window's `QStackedWidget` (chat / settings) is replaced by the app's
  **tabbed** shell; this file is refactored into `ui/floating_window.py` (mini) and
  the chat page becomes **Tab 1 (Voice Chat)**.
- `core/chat.py`'s direct OpenAI call is **superseded by the orchestrator**, which
  can *also* answer plainly but owns tool routing. Keep `chat.py` as the
  "no-tools fast answer" path the orchestrator may call.

**Verdict:** the visual/voice heart of the product. Keep, refactor into shell + tab.

---

## 2. `terminal_access_module/` — the agent brain  → **KEEP (becomes the orchestrator core)**

**Stack:** PyQt6 · Ollama + OpenAI providers · persistent PowerShell · permission engine · SQLite fast-path memory · pytest.

This is the **most valuable** module and the closest thing to the "controller hub"
the user described. Almost all of it is reused.

**What's good and stays:**
- [`providers/base.py`](terminal_access_module/providers/base.py) — the `AIProvider`
  abstraction (`list_models` / `chat(tools=…)` / `chat_stream` / `supports_tools`).
  This is exactly the seam that lets us keep ChatGPT default + Ollama fallback.
- [`providers/openai_provider.py`](terminal_access_module/providers/openai_provider.py)
  — full **tool/function-calling** support. The orchestrator runs on this.
- [`agent/agent.py`](terminal_access_module/agent/agent.py) — the ReAct loop
  (QThread) with loop-detection, retry hints, output truncation, intent fallback.
  **Generalized** from "PowerShell-only" to "many tools" → becomes the orchestrator.
- [`tools/powershell.py`](terminal_access_module/tools/powershell.py) — persistent
  `QProcess` shell with base64 wrapping + UUID capture markers. The terminal tool.
- **The whole `permissions/` package** — this *is* the "Auto / Manual / Partial +
  read-the-meaning-and-confirm" feature the user wants:
  - [`permissions/safety.py`](terminal_access_module/permissions/safety.py) —
    regex risk classifier → `(RiskLevel, RiskCategory, human reason)`.
  - [`permissions/policy.py`](terminal_access_module/permissions/policy.py) —
    Manual/Partial/Auto decision.
  - [`permissions/manager.py`](terminal_access_module/permissions/manager.py) —
    confirm-callback orchestration.
  - [`ui/permission_dialog.py`](terminal_access_module/ui/permission_dialog.py) —
    the modal. Extended to be **voice-answerable**.
- [`memory/command_memory.py`](terminal_access_module/memory/command_memory.py) —
  SQLite fast-path (skip the LLM for known commands). Keep.
- [`ui/chat_panel.py`](terminal_access_module/ui/chat_panel.py) — the reference for
  wiring agent ↔ permission ↔ terminal with thread-safe hand-off. Its patterns move
  into the orchestrator + Tab 1.
- [`ui/terminal_panel.py`](terminal_access_module/ui/terminal_panel.py) → **Tab 3 (Terminal)**.
- `tests/` — the pytest suite (policy, safety, memory, providers, agent). Keep and grow.

**What changes:**
- `agent.py` is generalized: today it only knows `run_powershell`. It becomes a
  tool-agnostic loop that takes a **tool registry** (see MODULE_CONTRACT.md).
- The `infer_action_command()` heuristic in `agent.py` (hard-coded "open youtube"
  etc.) is a crutch for weak models — with the ChatGPT default it becomes a small
  safety net, not the main path.

**Verdict:** the engine room. Keep almost entirely; generalize the agent.

---

## 3. `timeline_monitor_module/` — activity recall  → **KEEP ENGINE / PORT UI**

**Stack:** PySide6 (UI only) · SQLAlchemy + SQLite/WAL · FTS5 · FastAPI localhost · FAISS semantic · Chrome/Edge MV3 extension.

This delivers **Tab 2 (Activity Timeline)** and powers every "recall / reopen"
request. Crucially, its engine is **Qt-free** — verified: only 6 files import
PySide6, all under `recall/ui/`.

**Engine — KEEP AS-IS (no Qt, moves in untouched):**
- `recall/capture/` — foreground-window polling → sessions (threading, not QThread).
- `recall/db/` — models, WAL engine, migrations, FTS5.
- `recall/storage/repository.py` — the single read/write gateway.
- `recall/search/` — query parsing (time/type/domain/app filters) + FTS5 search.
- `recall/semantic/` — FAISS + sentence-transformers, lazy/optional.
- `recall/files/` — Windows Recent-Items harvesting.
- `recall/api/server.py` — token-secured `127.0.0.1` FastAPI for the extension.
- `recall/resource/` — the reopener (URL / file / switch-to-window / launch exe).
- `recall/config.py`, `recall/logging_setup.py`.
- `extension/` — the Chrome/Edge connector (this is the "Chrome awareness").

**UI — PORT PySide6 → PyQt6 (6 files, mechanical):**
| File | Port work |
|------|-----------|
| `recall/ui/app.py` | tray/app bootstrap → merged into the Runner |
| `recall/ui/main_window.py` | sections list → **Tab 2** content |
| `recall/ui/workers.py` | `Signal`→`pyqtSignal`, `Slot`→`pyqtSlot` |
| `recall/ui/settings_page.py` | same signal swap + import changes |
| `recall/ui/result_item.py` | import changes |
| `recall/ui/theme.py` | none (pure stylesheet), just import path |

Port pattern for all: `from PySide6.QtCore import Signal, Slot` →
`from PyQt6.QtCore import pyqtSignal, pyqtSlot`, `QApplication.exec_`→`exec`, enum
access is already Qt6-style. Estimated: **half a day**.

**Verdict:** keep the engine verbatim, port 6 UI files. This is why PyQt6 wins —
porting *toward* PyQt6 is far less code than porting voice+terminal to PySide6.

---

## 4. `other tools to check/`  → mostly **ARCHIVE**, one **REUSE LOGIC**

| Item | What it is | Fate |
|------|-----------|------|
| [`jarvis_overlay_phase1.py`](other%20tools%20to%20check/jarvis_overlay_phase1.py) | A prettier PySide6 **QML** floating orb — but dummy (no real audio). | **ARCHIVE as design reference.** The PyQt6 floating window is functional; don't introduce QML. Borrow the *look* (pulse rings, glass) later. |
| `jarvis_voice/` | Older voice module (`voice/stt.py`, `tts.py`, `audio_io.py`). | **ARCHIVE.** Superseded by `jarvis_voice_core`. |
| [`start_run.py`](other%20tools%20to%20check/start_run.py) + `startup_profiles.json` | wxPython **startup-profiles launcher** (Default/Coding/Personal/Failsafe → lists of apps, 5s auto-load countdown). | **REUSE LOGIC.** The idea (named profiles that launch app-sets) is genuinely useful → reimplement as an optional "Profiles" feature in Qt (Phase 7). Drop the wxPython UI; keep `_launch_many` logic. |

---

## Cross-cutting findings (the things that shape the whole merge)

### F1 — Qt binding clash (the blocker)
PyQt6 (voice, terminal) vs PySide6 (timeline UI, overlay) cannot share a process.
**Resolution: standardize on PyQt6**, port the 6 timeline UI files. Overlay QML is
archived. See README "The one big technical decision".

### F2 — Third and fourth UI toolkits exist
`start_run.py` is wxPython; the overlay is QML. Neither survives into the app —
we consolidate on **PyQt6 Widgets** only.

### F3 — Two chat paths, one brain wanted
`voice_core/core/chat.py` (streaming, no tools) and `terminal/agent+providers`
(tool-calling) are two brains. The merge keeps **one orchestrator** (tool-calling)
that can also answer plainly. Voice's streaming/TTS wraps the orchestrator's output.

### F4 — Two SQLite DBs + one vector index already
`commands_memory.db` (terminal) and `activity.db` (timeline) + optional FAISS.
The merge keeps these and **adds** tables/DBs for reminders, structured logs, and
conversation history — all SQLite. One shared data directory under
`%LOCALAPPDATA%`. No Redis, no Chroma needed (see README data-layer table).

### F5 — Permissions are already the feature the user described
The Auto/Manual/Partial modes + semantic risk reason + confirm dialog already
exist in the terminal module. The only *new* work is making confirmation
**voice-answerable** and routing **all** tools (not just PowerShell) through it.

### F6 — Wake word is not truly always-on
Current wake word is a **post-STT string match**, so the mic already has to be
listening. "Multiple wake words in settings" is easy on top of this. A genuine
always-on hotword (openWakeWord / Vosk / Porcupine) is a **later enhancement**,
noted in the roadmap — not required for v1.

### F7 — Reminders do not exist
Grep confirms no scheduler anywhere. Reminders is a **net-new module** (Phase 4):
NL datetime → SQLite → background scheduler → popup + TTS.

### F8 — Power & Chrome awareness are small additions
- **Power:** a thin tool over `psutil.sensors_battery()` + PowerShell power actions
  (sleep/shutdown/lock already classifiable by the safety engine).
- **Chrome:** already captured in `browser_visits` via the extension + local API.
  The hub just needs a `browser_recall` tool over that table; optional live
  "current tab" endpoint can be added to the extension later.

---

## Reuse scorecard

| Capability the user asked for | Already built? | Where it comes from |
|-------------------------------|----------------|---------------------|
| Floating window + orb | ✅ | voice_core |
| Voice in (STT) + voice out (TTS) + wake word | ✅ (wake = basic) | voice_core |
| Text + voice chat controller (Tab 1) | ⚙️ assemble | orchestrator = terminal agent + voice I/O |
| ChatGPT API + JARVIS persona + capability awareness | ✅ persona / ⚙️ capabilities | voice_core persona + new system prompt |
| Terminal access + view commands/logs (Tab 3) | ✅ | terminal_access_module |
| Activity monitor timeline (Tab 2) | ✅ | timeline_monitor_module |
| Detailed execution logs (Tab 4) | ⚙️ new viewer over existing logs | new + terminal/timeline logs |
| Recall docs / reopen / "watching Lantern on Hotstar" | ✅ | timeline search + resource reopener |
| Chrome activity awareness | ✅ | timeline extension + browser_visits |
| Permission Auto/Manual + confirm | ✅ | terminal permissions |
| Voice-answerable confirmation | ⚙️ extend | permission_dialog + STT |
| Power awareness | 🆕 small | new power tool |
| Reminders (spoken → popup) | 🆕 | new reminders module |
| Global + per-module settings (Tab 5) | ⚙️ unify | each module has settings today |
| Upgradable, add-more-modules design | 🆕 | module contract (MODULE_CONTRACT.md) |
| Dashboard (coming soon) | 🆕 stub | placeholder tab |

Legend: ✅ exists · ⚙️ assemble/adapt existing · 🆕 net-new.

**Bottom line:** ~70% of the product already exists in working code. The merge is
mostly *integration + one Qt port + three small new modules (reminders, power,
orchestrator glue)* — not a rewrite.
