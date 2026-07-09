# STATUS — What's built and verified

_Last updated: Phases 0, 1, 2, and 3 complete._

The unified app lives under **`jarvis/`**. The three original module folders are
kept intact as the source of truth; nothing was deleted.

```powershell
pip install -r jarvis/requirements.txt
python -m jarvis
```

---

## Phase 0 — Foundation ✅

**Built**
- `jarvis/` package with a clean kernel under `jarvis/app/`:
  - `config/paths.py` — data dir at `%LOCALAPPDATA%\Jarvis\`
  - `config/settings.py` — JSON global settings (+ per-module namespaces), writes defaults on first run
  - `data/db.py` — shared SQLite (WAL) `jarvis.db`
  - `logsetup.py` — rotating file + console logging with secret scrubbing
  - `bus.py` — in-process publish/subscribe event bus
  - `registry.py` — the `Module` / `Tool` / `AppContext` contract + `ModuleRegistry`
- The three modules copied under `jarvis/modules/{voice,terminal,timeline}` with
  imports rewritten to the package root (terminal: 28 files re-rooted; voice &
  timeline engines needed none).

**Verified**
- Bus unit test (publish → subscriber; `once`; unsubscribe) passes.
- `%LOCALAPPDATA%\Jarvis\` created with `config.json` (defaults) + `jarvis.db` (WAL).
- All 21 moved engine modules import cleanly from the new package root.

## Phase 1 — Qt unification + tabbed shell ✅

**Built**
- **Timeline UI ported PySide6 → PyQt6** (4 files: `main_window`, `settings_page`,
  `result_item`, `workers`) — enum scoping fixed (`Qt.ItemDataRole.UserRole`,
  `QMessageBox.StandardButton.*`, etc.). The timeline **engine was untouched**.
- `jarvis/ui/`:
  - `main_window.py` — `QTabWidget` with **Voice Chat · Activity Timeline ·
    Terminal · Logs · Settings · Dashboard** (last three are phase-marked placeholders).
  - `floating_window.py` — frameless always-on-top orb with a **maximise** button
    that opens the tabbed window; collapse-to-orb; drag.
  - `tray.py` — system-tray icon + menu (Open / Pause tracking / Quit).
  - `voice_controller.py` — the shared voice/chat brain (one mic pipeline for both
    the orb and Tab 1).
  - `widgets/chat_view.py` — reusable conversation widget (bubbles, mic buttons).
  - `styles.py` — scoped stylesheets (glass / terminal / app chrome).
- `runner.py` — single-instance guard (QLocalServer), background service boot,
  tray, floating window, lazy main window.

**Verified**
- `python -m jarvis` boots end-to-end: kernel DB, timeline DB, **activity tracker,
  file service, and browser API (127.0.0.1:8123)** all start and stop cleanly, exit 0.
- All 6 tabs construct; **no PySide6 import remains** anywhere in `jarvis/`.
- Tab 2 shows **real captured activity** (59 sessions / 91 files on this machine).
- Tab 3 runs a live PowerShell command (`sum=5`).
- Single-instance: a second launch detects and surfaces the first.

## Phase 2 — Orchestrator (the controller hub) ✅

**Built**
- `app/orchestrator.py` — a tool-calling ReAct loop on a `QThread`, generalised
  from the terminal agent; emits `status / tool_started / tool_finished / final`.
- `app/tool_router.py` — aggregates every module's tools into the OpenAI tool
  array, dispatches calls to handlers, normalises + truncates results.
- `app/prompts.py` — the JARVIS persona + **capability manifest** (what it can do,
  and to ask before opening one of many recall hits / before risky actions).
- `modules/terminal/module.py` — exposes `run_powershell` over a **GUI-thread
  bridge** so the worker-thread loop can call it synchronously; uses the **same
  engine as Tab 3**, so agent commands also appear in the live terminal.
- `modules/timeline/module.py` — `recall_search`, `recall_open`,
  `list_recent_files`, `browser_recall`; results are cached so "open the third
  one" resolves by index/ref; free-text time windows ("last 2 days") parsed.
- **OpenAI provider fix** — assistant `tool_calls` and matching `tool_call_id`s are
  now preserved across steps (they were being stripped, which would break any
  multi-step tool loop with the cloud model).
- `voice_controller.py` now routes chat through the orchestrator when configured
  (falls back to plain streaming otherwise); renders tool steps in `ChatView`;
  persists each turn to a `conversations` table.
- `runner.py` wires it all: shared PowerShell engine, module tools registered,
  OpenAI provider, and a **partial-mode permission gate** (read-only/safe commands
  run; risky PowerShell is declined until Phase 3 adds voice confirmation).

**Verified**
- Module discovery finds `terminal` + `timeline`; **5 tools registered**
  (`run_powershell`, `recall_search`, `recall_open`, `list_recent_files`,
  `browser_recall`).
- Real `recall_search("chrome")` returns actual past activity (Chrome windows,
  Amazon search) from the live DB — the "what was I doing" capability.
- The PowerShell bridge, called **from a worker thread**, returns real output
  (`xyz`) — proving the cross-thread marshalling the orchestrator relies on.
- Orchestrator loop with a mocked provider:
  - "what is Apple?" → answered directly, **no tools** called.
  - a tool request → tool dispatched with args, result fed back, final answer produced.
- Full `python -m jarvis` boot logs **"Orchestrator enabled (model=…, tools=5)"** and exits 0.

**Not yet (by design — later phases)**
- A live end-to-end call to the real ChatGPT API (needs the user's key + network;
  the loop is proven with a mock and the tools with real data).
- Streaming of the *final* tool-driven answer token-by-token (pure chat still
  streams; tool answers currently appear at once).

## Phase 3 — Permissions + voice confirmation ✅

**Built**
- `app/permissions.py` — `PermissionCoordinator`: classifies **every** tool call
  (PowerShell via the safety classifier; other tools via their `risk` hint) and
  applies **Auto / Partial / Manual** with the same rules as the terminal policy.
  Risky actions call a confirm broker; every decision is logged.
- `app/eventlog.py` — structured `event_log` table (ts, kind, module, summary,
  risk, decision) + bus publish; the audit trail and the Phase 6 Logs-tab feed.
- `ui/confirm_broker.py` — `ConfirmBroker`: on a required confirm it **speaks**
  "Sir, confirm … Should I proceed?", shows the modal `PermissionDialog`, and
  **listens for a spoken yes/no**; first of voice or click wins. Blocks the
  orchestrator's worker thread until answered (dialog's nested loop processes the
  queued STT result).
- **Mode toggle** in the ChatView (orb + Tab 1), persisted to global settings and
  synced across both surfaces; live-updates the coordinator.

**Verified**
- Partial: `recall_search` and `Get-Date` run **without** a prompt; `Stop-Process
  -Name WhatsApp` triggers a confirm whose reason reads *"Terminating or modifying
  running processes/services"* — spoken/clicked **no** declines, **yes** allows.
- Manual: read-only runs; a `safe_action` tool asks. Auto: everything runs, no prompt.
- Yes/no classifier: "yes please"→yes, "do it"→yes, "cancel that"→no, "don't"→no,
  "maybe later"→undecided (keeps listening).
- Every decision written to `event_log` with risk + outcome; mode set on the orb
  propagates to the coordinator **and** the Tab-1 toggle; full app boots (exit 0).

**Not yet (later phases)**
- The GUI modal + live mic yes/no need a display + microphone to exercise by hand
  (the decision plumbing, classifier, and modal component are each verified).

---

## How the pieces fit (as built)

```
python -m jarvis → Runner
  ├─ services: TrackerService · FileRecallService · ApiServer   (Qt-free threads)
  ├─ PowerShellEngine (shared)  ──────────────┐
  ├─ VoiceController ── configure_orchestrator │
  │     └─ Orchestrator (QThread) → ToolRouter ┤→ run_powershell (bridge → engine)
  │                                            ├→ recall_search / recall_open / …
  │                                            └→ browser_recall
  ├─ FloatingWindow (orb + ChatView)   ── request_maximise ─┐
  └─ Tray (Open / Pause / Quit)                             ▼
                                            MainWindow (6 tabs; Tab 3 uses the shared engine)
```

## Known follow-ups / debt
- `test_openai_provider_missing_key` fails **pre-existing** (the provider now
  allows an empty key at construction and raises on first use); update the test
  when the provider's contract is finalised.
- Keys still live per-module in `.env` (voice + terminal). Centralising them is
  **Phase 7** (settings unification).
- Timeline still stores under `%LOCALAPPDATA%\WindowsActivityRecall\` (option A,
  zero-migration). Fold into `Jarvis\` later only if a cross-DB join is needed.
