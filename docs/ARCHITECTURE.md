# ARCHITECTURE — Target design

How the merged app is put together: the process model, the folder structure, the
orchestrator, the permission flow, the event bus, and the data layer.

---

## 1. Process model — one Runner, many services

Everything lives in **one Python process** so the LLM, voice, terminal, capture,
and reminders share state without IPC. The Runner:

1. Acquires a **single-instance lock** (named mutex) — launching again just
   surfaces the existing window.
2. Boots background **services** (capture, browser API, reminder scheduler,
   PowerShell engine) via the module registry.
3. Creates the **tray icon** (no taskbar button) and the **floating orb**.
4. Lazily builds the **tabbed main window** on first maximise.
5. On quit: stops services in reverse order, flushes DB, releases the lock.

```
python -m jarvis      →  Runner
                          ├─ ServiceRegistry.start_all()        (background)
                          ├─ TrayIcon                            (open / pause / quit)
                          ├─ FloatingWindow (orb + Tab-1 chat)   (always available)
                          └─ MainWindow (tabs)                   (lazy, on maximise)
```

The floating orb and the main window **share one orchestrator instance and one
voice pipeline** — so a command started in the orb shows up in the Logs tab, and
vice-versa.

---

## 2. Folder structure

```
jarvis/                              # the single installable package
  __main__.py                        # `python -m jarvis` → Runner
  runner.py                          # single-instance, service boot, tray, windows, hotkeys

  app/                               # the shared "kernel" — binding-light, testable
    bus.py                           # in-process event bus (pub/sub) for module connectivity
    registry.py                      # ServiceRegistry + ModuleRegistry (discovery, lifecycle)
    orchestrator.py                  # LLM tool-router (generalized ReAct agent)
    tool_router.py                   # aggregates module tools → LLM tool specs + dispatch
    session.py                       # conversation state, history, turn model
    llm/
      base.py                        # AIProvider  (from terminal/providers/base.py)
      openai_provider.py             # ChatGPT, tool-calling  (from terminal)
      ollama_provider.py             # fallback  (from terminal)
    permissions/                     # from terminal/permissions/*  (safety, policy, manager)
      safety.py  policy.py  manager.py
      confirm.py                     # NEW: visual + voice-answerable confirmation broker
    config/
      settings.py                    # global settings (JSON) + typed access
      module_settings.py             # per-module settings namespaces (Tab 5 split)
      paths.py                       # %LOCALAPPDATA%\Jarvis\... data paths
    data/
      db.py                          # shared SQLite (WAL) engine + session factory
      fts.py                         # FTS5 helpers (reused across domains)
      migrations.py                  # schema versioning
    logging/
      structured.py                  # structured event log → SQLite (feeds Tab 4)
      files.py                       # rotating file logs

  modules/                           # each module is independently upgradable (see MODULE_CONTRACT.md)
    voice/                           # from jarvis_voice_core/core/*
      module.py                      # Module: exposes STT/TTS services + wake config
      stt.py  tts.py  wake.py
    terminal/                        # from terminal_access_module
      module.py                      # Module: exposes run_powershell tool + Terminal service
      powershell.py                  # persistent QProcess shell
      memory.py                      # fast-path command memory (SQLite)
    timeline/                        # from timeline_monitor_module (engine unchanged)
      module.py                      # Module: exposes recall_search / recall_open / list_files tools
      recall/                        # capture, db, storage, search, semantic, files, api, resource
    browser/                         # thin: reads timeline browser_visits + owns the extension link
      module.py                      # Module: exposes browser_recall / open_last_page tools
    reminders/                       # NEW
      module.py                      # Module: set/list/cancel reminder tools + scheduler service
      scheduler.py  store.py  parse.py
    power/                           # NEW (small)
      module.py                      # Module: battery/plan status + sleep/shutdown/lock tools
    dashboard/                       # stub — "coming soon"
      module.py

  ui/
    floating_window.py               # mini hub (orb + compact Tab-1)  — from voice_core
    main_window.py                   # QTabWidget shell
    tray.py                          # tray icon + menu  — merged from timeline/ui/app.py
    theme.py                         # one palette/stylesheet for the whole app
    tabs/
      voice_chat_tab.py              # Tab 1 — the controller hub (voice + text)
      timeline_tab.py                # Tab 2 — activity monitor (ported timeline UI)
      terminal_tab.py                # Tab 3 — live terminal + command view
      logs_tab.py                    # Tab 4 — detailed execution logs
      settings_tab.py                # Tab 5 — global + per-module settings
      dashboard_tab.py               # Dashboard (coming soon)
    widgets/
      chat_view.py  permission_prompt.py  orb.py  result_card.py

  extension/                         # Chrome/Edge MV3 connector (from timeline)

  tests/                             # pytest — grows the terminal suite to cover orchestrator

docs/                                # these planning docs
data/  (runtime, gitignored)         # DBs, FAISS index, logs — actually under %LOCALAPPDATA%\Jarvis
```

**Guiding rule:** `app/` and `modules/*/` engine code stay **UI-agnostic**; only
`ui/` and `modules/*/module.py` touch PyQt6. That keeps the kernel testable and
future ports cheap.

---

## 3. The orchestrator — Tab 1's brain

The orchestrator is the generalized version of
[`terminal_access_module/agent/agent.py`](terminal_access_module/agent/agent.py):
a ReAct loop on a worker thread that, instead of knowing only `run_powershell`,
receives the **full tool set** from the tool router and lets the LLM choose.

```
 user speech / text
        │  (STT if voice)
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ Orchestrator (QThread)                                       │
 │  system prompt = JARVIS persona + capability manifest        │
 │  history = last N turns                                      │
 │  tools = ToolRouter.specs()   ← all modules contribute       │
 │                                                              │
 │  loop up to MAX_STEPS:                                       │
 │    msg = provider.chat(model, messages, tools)               │
 │    if msg has tool_calls:                                    │
 │        for call in tool_calls:                               │
 │            PermissionManager.check(call)  ──▶ confirm broker  │
 │            result = ToolRouter.dispatch(call)                │
 │            messages += tool result                           │
 │            StructuredLog.record(call, result, decision)      │
 │        continue                                              │
 │    else:                                                     │
 │        final answer → stream to bubble + TTS                 │
 └─────────────────────────────────────────────────────────────┘
```

**Routing is emergent, not hard-coded.** "What's Apple?" → the model just answers
(no tool call). "Sleep my PC" → the model emits a `run_powershell` call. "List my
last 2 days of JD docs" → a `recall_search` call. The persona/system prompt tells
the model *what it can do*; the tool schemas tell it *how*.

**Capability manifest** (part of the system prompt) — the model is told, in plain
language, that it can: run terminal commands, recall/reopen past activity and
files, recall browser history, set reminders, check power/battery, and that some
actions require the user's confirmation. This is what makes it say *"I found 6
documents, which should I open?"* instead of guessing.

**Streaming + speech:** plain answers stream token-by-token into the chat bubble
and are spoken sentence-by-sentence (reusing voice_core's `SpeechQueue` flushing).
Tool-driven turns speak the final summary.

---

## 4. Tool router & the tool contract

Every module contributes tools through the **ModuleRegistry** (see
MODULE_CONTRACT.md). A tool = an OpenAI function spec **plus** a Python handler:

```python
Tool(
    spec={
        "type": "function",
        "function": {
            "name": "recall_search",
            "description": "Search the user's own past activity (apps, windows, "
                           "browser pages, files) by keywords and time. Use for "
                           "'what was I doing', 'documents I opened', 'find the page…'.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "since":  {"type": "string", "description": "e.g. 'last 2 days'"},
            }, "required": ["query"]},
        },
    },
    handler=timeline_module.recall_search,   # returns a JSON-able result
    risk="read_only",                        # hint for the permission layer
)
```

The router:
- **aggregates** all module tool specs into the array passed to `provider.chat`;
- **dispatches** a tool call to the owning handler;
- **normalizes** results to compact JSON/text (truncated) for the next LLM step;
- **tags** each call with a risk hint so the permission layer can act even on
  non-PowerShell tools (e.g. `recall_open` that launches an app).

---

## 5. Permission & confirmation flow

Reuses the terminal permission engine, extended for **all** tools and **voice**.

```
 tool call proposed
        │
        ▼
 PermissionManager.check(command_or_action, risk_hint)
        │
        ├─ AUTO      → allow (guardrails still classify + log)
        ├─ PARTIAL   → allow read-only / safe launches; else → confirm
        └─ MANUAL    → allow only read-only; else → confirm
                                   │
                                   ▼
                        ConfirmBroker.ask(summary, reason, risk)
                          │  speaks:  "Sir, confirm — close WhatsApp?"
                          │  shows:   modal with Allow / Reject
                          │  accepts: voice "yes"/"no"  OR  click
                          ▼
                     allowed? → dispatch : skip (logged as declined)
```

Key points:
- The **reason** shown/spoken comes from
  [`permissions/safety.py`](terminal_access_module/permissions/safety.py)'s human
  explanation ("File or directory deletion", "System shutdown or restart").
- The "**close web → close WhatsApp?**" case: the model's chosen action is
  summarized back to the user *before* execution in Manual/Partial, so a
  mis-heard/mis-inferred action is caught by the human, by voice.
- `ConfirmBroker` marshals to the GUI thread (the thread-safe hand-off pattern
  already proven in
  [`ui/chat_panel.py`](terminal_access_module/ui/chat_panel.py)) and *also* arms
  the STT for a yes/no.

---

## 6. Event bus — how modules stay connected yet independent

A tiny in-process pub/sub (`app/bus.py`). Modules never import each other; they
publish and subscribe to typed events. This is what makes each module
**upgradable in isolation**.

Example events:
| Event | Publisher | Subscribers |
|-------|-----------|-------------|
| `voice.utterance` | voice | orchestrator |
| `tool.executed` | tool router | logs, timeline |
| `permission.decided` | permission mgr | logs |
| `reminder.due` | reminders | ui (popup), voice (TTS) |
| `activity.session_ended` | timeline capture | dashboard (future) |
| `power.state_changed` | power | ui, orchestrator context |

The bus is synchronous-by-default with an async option; UI subscribers marshal to
the GUI thread. Keeping the surface tiny (publish/subscribe/once) avoids it
becoming a dumping ground.

---

## 7. Data layer

One data directory: `%LOCALAPPDATA%\Jarvis\` (mirrors timeline's current scheme).

```
%LOCALAPPDATA%\Jarvis\
  jarvis.db            SQLite (WAL) — the shared DB
  activity.db          (option A) keep timeline's DB separate, or (option B) fold in
  semantic.index       FAISS vector index (+ semantic_map.json)
  faiss/               vector artifacts
  config.json          global settings
  modules/<id>.json    per-module settings
  api_token.txt        browser-extension pairing token
  logs/jarvis.log      rotating file log
```

**Tables (SQLite + FTS5):**
- From timeline (unchanged): `applications`, `sessions`, `browser_visits`,
  `file_events`, `resources`, `search_fts`.
- From terminal (unchanged): command memory (fast-path patterns).
- **New:**
  - `reminders(id, text, fire_at, created_at, status, recurrence, source)`
  - `event_log(id, ts, kind, module, summary, detail_json, risk, decision)` — the
    structured feed for **Tab 4 (Logs)**, also FTS-indexed for search.
  - `conversations(id, ts, role, content, tool_name, meta_json)` — hub history.

**Search stays unified:** FTS5 for keyword (`event_log`, activity, history);
FAISS for semantic recall (already built in `recall/semantic/`). No Redis (single
process → in-memory queues + `QThread` signals). No Chroma (FAISS covers vectors;
if we ever want Chroma it hides behind the same `recall/semantic/service.py` API).

**DB decision (A vs B):** start with **option A** — keep timeline's `activity.db`
as its own file (zero migration risk) and put new tables in `jarvis.db`. Both use
WAL and live in the same folder. Consolidate later only if a cross-DB join is
actually needed (it isn't for v1).

---

## 8. Threading model

- **GUI thread:** all PyQt6 widgets, tray, dialogs.
- **Orchestrator:** its own `QThread` (already the pattern in `agent.py`); emits
  signals for chunks/results/final.
- **PowerShell:** `QProcess` (async, non-blocking) on the GUI thread's event loop.
- **Capture / browser API / reminder scheduler:** plain daemon `threading.Thread`
  (already how timeline runs) — Qt-free, so no cross-binding issues.
- **STT/TTS:** worker tasks via `QThreadPool` (voice_core's pattern).
- **Rule:** engine threads never touch widgets; they publish on the bus or emit
  signals, and UI subscribers marshal back to the GUI thread.

---

## 9. Configuration & the split settings (Tab 5)

- `app/config/settings.py` holds **global** settings (LLM model, default
  permission mode, wake words, theme, autostart).
- Each module declares a **settings schema**; `module_settings.py` persists them
  per-module (`modules/<id>.json`).
- **Tab 5** renders global settings first, then one collapsible section per
  module built from its schema — so settings are "split module-wise" exactly as
  asked, while staying in one place. API keys still land in `.env`
  (voice_core/terminal convention) for secrets.

---

## 10. Where each requested tab's content comes from

| Tab | Source | New work |
|-----|--------|----------|
| 1 · Voice Chat (hub) | voice_core chat page + orchestrator + terminal permission wiring | assemble + capability prompt |
| 2 · Activity Timeline | timeline `recall/ui/main_window.py` (ported) | PySide6→PyQt6 port |
| 3 · Terminal | terminal `ui/terminal_panel.py` | drop-in |
| 4 · Logs | new viewer over `event_log` table | new widget |
| 5 · Settings | new shell + each module's schema | new shell, reuse module settings |
| Dashboard | stub | "coming soon" placeholder |

See **[docs/ROADMAP.md](docs/ROADMAP.md)** for the order this gets built in.
