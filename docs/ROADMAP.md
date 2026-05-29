# ROADMAP — The phased build plan

Nine phases, each shippable and testable on its own. Every phase lists its
**Goal**, **Tasks**, **Deliverables**, and **Acceptance** (how you *know* it's
done). Do them in order — later phases assume the kernel from earlier ones.

Rough sizing is relative effort (S / M / L), not calendar promises.

| Phase | Theme | Size | Status |
|-------|-------|------|--------|
| 0 | Foundation & scaffolding | M | ✅ **done** |
| 1 | Qt unification + tabbed shell | M | ✅ **done** |
| 2 | Orchestrator (the controller hub, Tab 1) | L | ✅ **done** |
| 3 | Permissions + voice confirmation | M | ✅ **done** |
| 4 | Reminders module | M | ⏳ next |
| 5 | Power + Chrome recall + wake words | M | |
| 6 | Logs tab + Timeline polish + Dashboard stub | M | |
| 7 | Settings unification + module-contract hardening | M | |
| 8 | Packaging, resilience, autostart | M | |

> Progress detail and verification evidence: **[docs/STATUS.md](STATUS.md)**.

---

## Phase 0 — Foundation & scaffolding
**Goal:** one runnable process skeleton that everything else grows inside.

**Tasks**
- Create the `jarvis/` package and the folder structure from ARCHITECTURE.md.
- One merged virtualenv + `requirements.txt` (PyQt6, openai, sounddevice, numpy,
  pywin32, SQLAlchemy, pydantic, fastapi, uvicorn, psutil, dateparser; FAISS +
  sentence-transformers optional).
- `app/config/paths.py` → `%LOCALAPPDATA%\Jarvis\`; `app/data/db.py` (WAL engine);
  `app/logging/` (file + structured stub).
- `app/bus.py` (publish/subscribe/once) and `app/registry.py`
  (Module + Service + Tool + AppContext dataclasses) per MODULE_CONTRACT.md.
- `runner.py`: single-instance lock, empty service boot, tray icon, and it opens
  the **existing voice floating window** as-is (proves the process runs).
- Move the three modules under `modules/` (copy, don't delete originals yet);
  fix imports to package-relative. **Do not port PySide6 yet** — timeline stays
  importable as engine-only in this phase.

**Deliverables:** `python -m jarvis` launches; tray icon present; floating window
shows; shared DB + config created on first run.

**Acceptance**
- Launching twice surfaces the same window (single-instance works).
- `%LOCALAPPDATA%\Jarvis\` is created with `config.json` + empty `jarvis.db` (WAL).
- Bus unit test: publish → subscriber receives.

---

## Phase 1 — Qt unification + tabbed shell
**Goal:** all UIs live under PyQt6 in one window with the six tabs.

**Tasks**
- **Port `timeline/recall/ui/*` PySide6 → PyQt6** (6 files; `Signal→pyqtSignal`,
  `Slot→pyqtSlot`, import swaps, `exec_→exec`). Keep the timeline **engine
  untouched**.
- Build `ui/main_window.py` as a `QTabWidget` with: Voice Chat, Activity Timeline,
  Terminal, Logs, Settings, Dashboard (last one "coming soon" placeholder).
- Wire tabs to existing content: Tab 2 = ported timeline window; Tab 3 = terminal
  `terminal_panel.py`; Tab 1 = voice_core chat page (still standalone chat for now).
- `ui/tray.py`: merge timeline's tray (open / pause tracking / quit).
- Floating orb ↔ main window: **maximise** button on the orb opens/raises the
  tabbed window; minimising the window returns to the orb; both stay in one process.
- One `ui/theme.py` palette for the whole app.

**Deliverables:** the full tabbed control centre, opened from the orb or tray.

**Acceptance**
- Tab 2 shows **real captured activity** (start the capture service; open some
  apps; they appear).
- Tab 3 runs a live PowerShell command and shows output.
- Tab 1 still does voice + text chat (pre-orchestrator).
- No `PySide6` import remains anywhere (`grep` is clean); app runs on PyQt6 only.

---

## Phase 2 — Orchestrator (the controller hub, Tab 1)  ★ the heart
**Goal:** one brain that takes voice/text and routes to tools or answers directly.

**Tasks**
- Generalize `terminal/agent/agent.py` into `app/orchestrator.py`: same ReAct
  loop, but tools come from `app/tool_router.py` (not a hard-coded PowerShell tool).
- `app/tool_router.py`: aggregate `module.tools()` into the OpenAI tool array;
  dispatch calls to handlers; normalize + truncate results for the next step.
- Register the first tool set: `run_powershell` (terminal), `recall_search` /
  `recall_open` / `list_recent_files` (timeline), `browser_recall` (browser).
- Write the **JARVIS system prompt** = persona (from voice_core) + **capability
  manifest** (it can run terminal, recall activity/files/browser, and must ask
  before state-changing actions; when recall returns many hits, summarize and ask
  which to open).
- Tab 1 wiring: STT/text input → orchestrator → streamed reply into the bubble +
  sentence-by-sentence TTS (reuse `SpeechQueue`). Tool-driven turns speak the
  final summary. Show tool steps inline (reuse chat_panel's "show steps").
- Conversation history persisted to `conversations` table.

**Deliverables:** Tab 1 is the working controller hub; the orb uses the same
orchestrator.

**Acceptance** (the user's own examples become tests)
- "What's Apple?" → spoken answer, **no** tool call.
- "List the documents I opened in the last 2 days about JD" → `recall_search`
  runs, returns matches, and Jarvis replies *"I found N, which should I open?"*.
- "Open the third one" → `recall_open` launches file/URL/switches window.
- "I was watching Lantern on Hotstar, open it" → `browser_recall` finds the
  Hotstar visit newest→oldest and reopens the URL.
- A command started in the **orb** appears in the same conversation as the tab.

---

## Phase 3 — Permissions + voice confirmation
**Goal:** Auto / Partial / Manual across **all** tools, confirmable by voice.

**Tasks**
- Route every tool dispatch through `permissions/manager.py` using the tool's
  `risk` hint + (for PowerShell) `safety.py`'s classifier.
- `permissions/confirm.py` (ConfirmBroker): on a required confirmation, **speak**
  the summary + reason ("Sir, confirm — close WhatsApp?"), show the modal
  (Allow / Reject), and **arm STT for yes/no**; first of voice/click wins.
- Global permission-mode toggle in the orb and Tab 1 (Auto / Partial / Manual),
  persisted; default **Partial**.
- Log every decision to `event_log` (`permission.decided`).

**Deliverables:** the "it heard *close WhatsApp* — confirm?" safety flow, working
by voice and click.

**Acceptance**
- In **Manual**, a state-changing action (e.g. `Stop-Process`) triggers a spoken +
  visual confirm; saying "yes" runs it, "no" skips it (both logged).
- In **Partial**, read-only recall/searches run without prompting; a destructive
  action still prompts.
- The reason shown matches `safety.py` (e.g. "Terminating or modifying running
  processes/services").

---

## Phase 4 — Reminders module (net-new)
**Goal:** "remind me X at <time>" by voice → popup + spoken alert when due.

**Tasks**
- `modules/reminders/` per MODULE_CONTRACT.md: `store.py` (SQLite `reminders`),
  `parse.py` (NL datetime via `dateparser`, timezone-aware), `scheduler.py`
  (background thread; fires due reminders; supports snooze/recurrence later).
- Tools: `set_reminder`, `list_reminders`, `cancel_reminder`.
- `reminder.due` event → `ui/widgets` popup (always-on-top toast) + `ctx.speak`.
- Settings: popup on/off, speak on/off, default snooze.

**Deliverables:** end-to-end voice reminders with a visible popup.

**Acceptance**
- "Remind me to call the recruiter at 6pm" creates a reminder (verify in DB /
  `list_reminders`); at 6pm a popup appears **and** Jarvis speaks it.
- Survives app restart (scheduler reloads pending reminders from SQLite).
- "Cancel my 6pm reminder" removes it.

---

## Phase 5 — Power awareness + Chrome recall + wake words
**Goal:** the remaining "awareness" the hub needs, plus configurable wake.

**Tasks**
- `modules/power/`: `get_power_status` (psutil battery %, plugged, time-left; power
  plan via PowerShell) and actions `sleep` / `shutdown` / `lock` (routed through
  permissions; "sleep in 10s" schedules via reminders/scheduler or a delayed call).
- `modules/browser/`: `browser_recall(query, since)` over `browser_visits`
  (newest→oldest); `open_last_page(query)`. (Optional) extend the extension with a
  `current tab` endpoint for live awareness.
- **Wake words:** move wake config to global Settings; support **multiple** wake
  phrases (list). Keep the current post-STT gating; add optional always-on hotword
  (openWakeWord/Vosk) behind a setting as a stretch — not required to pass.

**Deliverables:** power/battery answers, live-ish Chrome recall, multi-wake config.

**Acceptance**
- "How much battery do I have?" → correct % + charging state.
- "Sleep my PC in 10 seconds" → confirm (per mode) → sleeps after 10s.
- Settings holds ≥2 wake phrases; either triggers a response in live mode.
- "Open the Hotstar page I was on" works via `browser_recall` (Phase 2 example now
  backed by the dedicated tool + extension data).

---

## Phase 6 — Logs tab + Timeline polish + Dashboard stub
**Goal:** full visibility into what Jarvis did; timeline feels first-class.

**Tasks**
- `event_log` structured logging everywhere (tool calls, args, results, permission
  decisions, errors, module versions at boot); FTS-index it.
- **Tab 4 (Logs):** filterable table/timeline — time, module, command/tool, result,
  risk, decision; click a row for full detail; search box (FTS).
- **Tab 2 polish:** ensure recall from the hub and the timeline UI share the same
  data and "reopen" behavior; add "send to Jarvis" from a result.
- **Dashboard tab:** real placeholder ("coming soon") with the intended layout
  sketched (usage stats, active reminders, power, recent actions).

**Deliverables:** a real audit/log view; polished timeline; dashboard placeholder.

**Acceptance**
- Every executed command/tool from Tabs 1/3 appears in Tab 4 with full detail and
  its permission decision.
- Searching the Logs tab (e.g. "Stop-Process") finds matching entries.
- Dashboard tab renders "coming soon" without breaking the tab bar.

---

## Phase 7 — Settings unification + module-contract hardening
**Goal:** one Settings tab, split module-wise; adding a module needs no core edits.

**Tasks**
- **Tab 5 (Settings):** global section (LLM/model, default mode, wake words, theme,
  autostart) + one auto-built section per module from `settings_schema()`; modules
  with a custom `settings_widget()` render that instead.
- Secrets (API keys, tokens) stay in `.env`; everything else in JSON namespaces.
- Formalize discovery/lifecycle/versioning; write the "add a module" recipe test:
  a throwaway stub module registers a tool + a tab + a setting **with no edits to
  the shell/orchestrator**.
- (Optional) fold in the **Startup Profiles** concept from `other tools/start_run.py`
  as a small module (named app-sets you can launch by voice: "load my coding profile").

**Deliverables:** unified settings; proven plug-in path.

**Acceptance**
- Every module's settings appear under Tab 5 and persist across restart.
- The stub-module test passes: dropping a module folder makes its tool callable by
  the orchestrator and its tab appear — no other file changed.

---

## Phase 8 — Packaging, resilience, autostart
**Goal:** a real installable app that survives errors and starts with Windows.

**Tasks**
- First-run **setup wizard**: collect OpenAI + Sarvam keys, generate the browser
  token, walk through loading the extension.
- Crash resilience: a failing module `start()` is logged and skipped; per-tick
  try/except in loops (already the timeline pattern) extended app-wide.
- **Autostart on login** (Startup shortcut / Task Scheduler), start-minimized to
  tray, no taskbar button.
- Package with **PyInstaller** (bundle pywin32, SAPI, FAISS optional); test on a
  clean Windows profile.
- Final pass: docs, `--headless` mode (services without UI), telemetry-free.

**Deliverables:** a distributable Jarvis that boots to the tray on login.

**Acceptance**
- Fresh machine: install → first-run wizard → keys set → orb + tray appear.
- Killing/raising an exception in one module doesn't crash the app; the rest work.
- Reboot → Jarvis is running in the tray automatically.

---

## Testing strategy (runs through every phase)
- **Keep and grow the terminal pytest suite** (`permissions`, `safety`, `memory`,
  `providers`, `agent`) → add `orchestrator`, `tool_router`, `reminders`, `bus`.
- **Golden intent tests:** the user's example utterances (Apple / JD docs / Hotstar
  / battery / reminder / close-WhatsApp-confirm) as scripted end-to-end checks with
  a mocked LLM returning canned tool calls — so routing + permissions are verified
  without spending API calls.
- **Qt-free kernel:** `app/` and module engines import no PyQt6, so they unit-test
  headless in CI.

## Decisions to confirm before Phase 1 coding
These are baked into the plan as recommendations; flag now if you disagree:
1. **PyQt6** as the single Qt binding (port timeline UI, archive QML overlay). ✅ recommended
2. **ChatGPT API** as the default brain; Ollama stays a selectable fallback. ✅ (matches your Ollama-accuracy finding)
3. **SQLite + FTS5 + FAISS + JSON**, no Redis/Chroma. ✅ recommended
4. Keep timeline's `activity.db` separate from `jarvis.db` for v1 (option A). ✅ recommended
5. Always-on hotword (openWakeWord) is a **stretch** in Phase 5, not a v1 blocker.

## Suggested first sprint
Phase 0 + Phase 1 together give you a single app with all tabs and real data —
the most motivating milestone. Then Phase 2 is where it becomes *Jarvis*.
