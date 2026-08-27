<h1 align="center">◭ JARVIS</h1>
<p align="center"><b>A private, agentic operator for your Windows PC — it runs real commands, remembers everything you do, and asks before it touches anything that matters.</b></p>

---

Most "AI assistants" are a microphone taped to a chatbot: you talk, it talks
back, and nothing on your computer ever changes. **JARVIS is built the other way
around — as an agent with hands and a memory, not a talking FAQ.**

- 🛠 **It acts, for real.** It writes and executes live **PowerShell** on a
  persistent shell, opens apps, and drives the system — then answers *only* from
  the actual output. Execution, not suggestions.
- 🧠 **It remembers what you did.** A private, always-on **timeline** of every app,
  window, file, and web page you touch — searchable by keyword, by time, or by
  *meaning*. *"What was I working on Tuesday?"* · *"Reopen that article."* ·
  *"Which JD docs did I open this week?"* — and it reopens them.
- 🛡 **It's safe by construction.** A **semantic risk engine** reads the *intent* of
  each action and asks for a **spoken or clicked** confirmation before anything
  destructive — so "close the browser" never quietly becomes "kill WhatsApp."
- 🔒 **It's yours, on-device.** Activity, memory, and logs stay **local**
  (SQLite + FTS5 + FAISS). The only thing that leaves your machine is the prompt
  you send to the model.
- 🧩 **It's built to grow.** A real **module contract**, event bus, and tool-routing
  orchestrator — drop in a browser controller, a web-fetch tool, or your own
  module without touching the core.

**This is not a weekend voice-assistant demo.** It's a modular desktop
application: one tray-resident process, a floating orb you can talk or type to,
and a six-tab control centre — with the agent loop, the permission layer, and the
activity engine already working end-to-end (Phases 0–3 done).

---

### Read the docs in this order

| Doc | What it covers |
|-----|----------------|
| **[README.md](README.md)** (this file) | The vision, the merged shape, how to run, the tech decisions |
| **[docs/ANALYSIS.md](docs/ANALYSIS.md)** | What each existing module is, what we keep / port / drop, and why |
| **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** | Target folder structure, the orchestrator, permissions, the data layer |
| **[docs/MODULE_CONTRACT.md](docs/MODULE_CONTRACT.md)** | The plugin interface that makes every module independently upgradable |
| **[docs/ROADMAP.md](docs/ROADMAP.md)** | The phased build plan with acceptance criteria for each phase |

---

## The product in one picture

```
                        ┌───────────────────────────────────────────────┐
   system tray icon ──▶ │                  R U N N E R                   │  one process
   (no taskbar entry)   │  boots services · owns tray · global hotkeys   │
                        └───────┬───────────────────────────────┬───────┘
                                │                               │
                        ┌───────▼────────┐             ┌────────▼───────────┐
                        │ Floating Orb   │  maximise ▶ │  Full Tabbed Window │
                        │ (mini hub —    │ ◀ minimise  │                     │
                        │  voice + text, │             │  1 Voice Chat  ★hub │
                        │  still executes│             │  2 Activity Timeline│
                        │  everything)   │             │  3 Terminal         │
                        └───────┬────────┘             │  4 Logs             │
                                │                       │  5 Settings         │
                                │                       │  (Dashboard — soon) │
                                ▼                       └─────────┬───────────┘
                        ┌─────────────────────────────────────────▼──────────┐
                        │                 O R C H E S T R A T O R             │
                        │  LLM (ChatGPT API) + JARVIS persona + tool router   │
                        │  decides: answer directly  ·  or call a tool        │
                        └───┬───────┬───────────┬──────────┬─────────┬────────┘
                            │       │           │          │         │
                    ┌───────▼─┐ ┌───▼────┐ ┌────▼─────┐ ┌──▼─────┐ ┌─▼────────┐
                    │terminal │ │timeline│ │reminders │ │ power  │ │ browser  │
                    │(PowerSh)│ │(recall)│ │  (new)   │ │ (new)  │ │(chrome ext)│
                    └────┬────┘ └───┬────┘ └────┬─────┘ └───┬────┘ └────┬─────┘
                         └──────────┴─── PERMISSION LAYER ──┴───────────┘
                                    (Auto / Partial / Manual · voice-confirmable)
                                              │
                                    ┌─────────▼──────────┐
                                    │  Shared data layer  │
                                    │ SQLite(WAL)+FTS5 +  │
                                    │ FAISS + JSON config │
                                    └────────────────────┘
```

## What you'll be able to say

| You say… | What happens |
|----------|--------------|
| "Jarvis, what's Apple?" | Plain answer, spoken back. No tools. |
| "Sleep my PC in 10 seconds." | Orchestrator → terminal tool; in Manual mode it confirms first ("Sir, confirm sleep in 10s?"). |
| "List the documents I opened in the last 2 days about the company JD." | Timeline recall → returns the matches → "I found 6, which should I open?" |
| "Open that one." / "Open the third." | Resource reopener launches the file / URL / switches to the window. |
| "I was watching *Lantern* on Hotstar — open it." | Browser recall searches visit history newest→oldest, finds the Hotstar tab, reopens the URL. |
| "Remind me to call the recruiter at 6pm." | Reminders module parses the time, schedules it, and fires a popup + voice at 6pm. |
| "How much battery do I have?" | Power tool reports charge / plan / time remaining. |
| "Close web." (it hears "close WhatsApp") | Permission layer reads the *meaning* and asks "Sir, should I close WhatsApp?" — you answer by voice or click. |

---

## 🖥️ Terminal module — your PC, under command

Ask in plain English; JARVIS writes and runs the right **PowerShell** on a real,
persistent shell and answers **only from the actual output** — it never guesses
about your system.

**Things you can ask it**

| You say / type | What it runs / does |
|----------------|---------------------|
| "How much free space is on C?" | `Get-Volume C` → reports real free/total |
| "What's my IP and Wi-Fi network?" | `ipconfig` / `Get-NetConnectionProfile` |
| "Is Docker installed, and which version?" | probes the command, answers yes/no + version |
| "Show my top 5 memory-hungry processes." | `Get-Process \| Sort WS -desc \| Select -First 5` |
| "Open Settings / YouTube / VS Code / Notepad." | `Start-Process "ms-settings:"` / a URL / the app |
| "Lock the PC." · "Sleep in 10 seconds." · "Shut down." | guarded system actions (ask first — see below) |
| "Make a folder called Reports on my Desktop." | `New-Item` (confirmed in Partial/Manual) |
| "Delete temp.txt from Downloads." | `Remove-Item` — **always asks before destructive actions** |

**What makes it safe and fast**

- **Persistent session** — one long-lived PowerShell process keeps its working
  directory and state; commands are base64-wrapped with UUID markers so output is
  captured cleanly, even across prompts.
- **Risk-aware** — every command is classified (`READ_ONLY … DESTRUCTIVE`,
  `SAFE … CRITICAL`) with a plain-English reason ("File or directory deletion",
  "System shutdown or restart").
- **You hold the keys** — an **Auto / Partial / Manual** switch governs execution;
  anything risky triggers a **spoken + clickable confirm** ("Sir, confirm…?"),
  answerable by voice ("yes"/"no") or button.
- **Fast-path memory** — a question you've asked before skips the LLM entirely and
  re-runs the learned command instantly (it only ever learns from **successful,
  allowed** runs).
- **Nothing hidden** — the **Terminal tab** shows every command JARVIS runs, live,
  right next to commands you type yourself.

## 🕓 Activity recall — your own memory, searchable

JARVIS quietly remembers **what you actually used** — apps, windows, files, and
browser pages — so you can find and **reopen** anything later, by keyword, by time,
or by meaning. Everything stays **on your machine**.

**Things you can ask it**

| You say / type | What it does |
|----------------|--------------|
| "What was I doing yesterday afternoon?" | Builds a timeline of that window of time |
| "Find the documents about the company JD I opened this week." | Keyword + time recall → lists the matches |
| "Which PDFs did I open in the last 2 days?" | `list_recent_files` filtered by type + time |
| "That article about capturing system audio — open it." | Semantic recall (by *meaning*) → reopens the page |
| "I was watching *Lantern* on Hotstar — reopen it." | Browser recall, newest→oldest → opens the URL |
| "Switch me back to the VS Code window I had open." | Activates the already-running window (no new instance) |
| "Open the third one." | Reopens that item from the list it just showed you |

**What makes it work**

- **Quiet capture** — the active window (process, title, duration), recently used
  files (Windows *Recent Items*), and — with the bundled **Chrome/Edge extension** —
  the pages you actively view, all recorded with low overhead.
- **Two ways to find things** — a unified **FTS5 keyword** index across apps + pages
  + files (with `yesterday`, `last 2 days`, `type:pdf`, `domain:`, `app:` filters),
  plus optional **semantic search** (local embeddings + FAISS) that matches by
  meaning when you don't remember the exact words.
- **Smart reopen** — URLs open in the browser, files open in their default app, and
  apps **switch to the running window** (falling back to relaunching the exe).
- **Private by design** — 100% local; pause / private mode, per-app and per-domain
  exclusions, a retention window, and delete-selected / clear-all controls.

---

## Why cloud ChatGPT, not local Ollama

Local models (via Ollama) were tried and could not hit the accuracy needed for
reliable **tool routing + PowerShell generation + recall reasoning**. The
merged product uses the **ChatGPT API** as the default brain. The provider layer
(`AIProvider`) is kept abstract, so Ollama remains a selectable fallback and any
future local model can drop in without touching the orchestrator — but the
shipped default and the accuracy target assume the cloud model.

## The one big technical decision: Qt binding

- Voice hub + Terminal/agent are **PyQt6**.
- Timeline is **PySide6** — *but only its 6 `recall/ui/*` files*. Its whole
  engine (capture, DB, FTS5 search, semantic, browser API, reopener) is
  **pure Python with no Qt import**.
- The old overlay (`other tools/`) is PySide6+QML; the profiles launcher is wxPython.

You **cannot** load PyQt6 and PySide6 in the same process. **Decision:
standardize on PyQt6** and port only the 6 timeline UI files (mechanical:
`Signal→pyqtSignal`, `Slot→pyqtSlot`, import swaps). Everything else — the entire
timeline engine, the terminal agent, the voice core — moves in unchanged.
Rationale and the full port list are in [docs/ANALYSIS.md](docs/ANALYSIS.md).

## Data layer — what we actually need

You asked whether we need vector DB / SQL / SQLite / Chroma / Redis. The answer
for a single-machine desktop app:

| Need | Choice | Status |
|------|--------|--------|
| Structured data (activity, command memory, reminders, logs, conversations) | **SQLite (WAL)** | Already used (2 DBs today) |
| Keyword / full-text search | **SQLite FTS5** | Already used (unified index) |
| Semantic / "by meaning" recall | **FAISS** (local vector index) | Already integrated, lazy-loaded |
| Config & preferences | **JSON** | Already used |
| **Redis** | **Not used** | Overkill on one machine — use in-process queues + SQLite |
| **Chroma** | **Not needed** | FAISS already covers it; can swap later behind one interface |

So: **SQLite + FTS5 + FAISS + JSON.** No server database, no Redis.

## How it runs (working now — Phases 0–2)

```powershell
pip install -r jarvis/requirements.txt
python -m jarvis
```

The unified `jarvis/` app is built and verified end-to-end: one process, one tray
icon, a floating orb, a 6-tab control centre, and a tool-calling orchestrator
that already drives PowerShell + activity recall. See **[docs/STATUS.md](docs/STATUS.md)**
for exactly what's implemented and how it was verified.

- Starts activity capture, the browser API, the reminder scheduler, and the
  PowerShell engine in the background.
- Drops a **floating orb** on screen and a **tray icon** (no taskbar button).
- Click the orb's maximise button (or double-click the tray) → the **tabbed
  control centre**.
- The orb alone can still take voice/text and execute everything — the tabs are
  for detail, history and control.

Step-by-step run instructions (keys, first launch, the browser extension,
troubleshooting) are in **[run.md](run.md)**.

## Current status

| Piece | State |
|-------|-------|
| `jarvis_voice_core/` | ✅ Works standalone — floating voice window (Sarvam STT, SAPI TTS, OpenAI chat) |
| `terminal_access_module/` | ✅ Works standalone — agent + PowerShell + permission engine + fast-path memory + tests |
| `timeline_monitor_module/` | ✅ Works standalone — capture + recall + search + semantic + Chrome extension |
| `other tools to check/` | 🔎 Reference only — QML overlay (design ref), old voice (superseded), wx profiles launcher (concept to reuse) |
| **Unified `jarvis/` app** | ✅ _Phases 0–3 built & verified — tray + orb + 6 tabs + tool-calling orchestrator + Auto/Partial/Manual permissions with voice confirm (`python -m jarvis`)_ |

The originals (`jarvis_voice_core/`, `terminal_access_module/`,
`timeline_monitor_module/`) are kept intact as the source of truth; the merged
copy lives under `jarvis/`. See **[docs/STATUS.md](docs/STATUS.md)** for progress
and **[docs/ROADMAP.md](docs/ROADMAP.md)** for the remaining phases.
