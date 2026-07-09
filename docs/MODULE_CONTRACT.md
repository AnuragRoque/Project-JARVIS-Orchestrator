# MODULE CONTRACT — How every module plugs in (and stays upgradable)

The user's requirement: *"I can modify or upgrade each module independently —
voice, terminal, timeline, dashboard, reminders."* This document defines the
single interface every module implements so the Runner can discover, start, wire,
and expose it **without any module importing another**.

If you follow this contract, adding a "browser controller" or "web fetch" module
later is: drop a folder in `modules/`, implement `Module`, done — no edits to the
orchestrator, the UI shell, or other modules.

---

## 1. The `Module` interface

```python
# app/registry.py  (interface sketch)
from dataclasses import dataclass, field
from typing import Callable, Any

@dataclass
class Tool:
    spec: dict                       # OpenAI function-tool JSON schema
    handler: Callable[..., Any]      # (**kwargs) -> JSON-able result
    risk: str = "read_only"          # "read_only" | "safe_action" | "state_change" | "destructive"

@dataclass
class SettingField:
    key: str
    label: str
    kind: str                        # "bool" | "int" | "text" | "choice" | "secret"
    default: Any = None
    choices: list = field(default_factory=list)

class Module:
    id: str                          # unique, e.g. "reminders"
    name: str                        # human label for Settings/Logs
    version: str                     # semantic version — enables independent upgrade

    # ---- lifecycle (called by the Runner) --------------------------------
    def start(self, ctx: "AppContext") -> None: ...   # boot background services
    def stop(self) -> None: ...                        # graceful shutdown

    # ---- what the module offers (all optional) ---------------------------
    def tools(self) -> list[Tool]: return []           # exposed to the orchestrator
    def settings_schema(self) -> list[SettingField]: return []
    def tab(self) -> "QWidget | None": return None     # a main-window tab, if any
    def settings_widget(self) -> "QWidget | None": return None   # custom settings UI (else auto-built)

    # ---- event wiring (optional) -----------------------------------------
    def subscribe(self, bus: "EventBus") -> None: ...  # register pub/sub handlers
```

`AppContext` is the **only** thing a module receives — its dependencies come from
the kernel, never from sibling modules:

```python
@dataclass
class AppContext:
    bus: EventBus                    # publish/subscribe
    db: Database                     # shared SQLite session factory
    config: ModuleSettings           # this module's persisted settings namespace
    paths: Paths                     # data dir, logs dir, etc.
    llm: AIProvider                  # current provider (for modules that need it)
    log: Logger                      # structured + file logging
    speak: Callable[[str], None]     # TTS out (voice module provides the impl)
```

---

## 2. Registration & discovery

```python
# modules/reminders/module.py
def get_module() -> Module:
    return RemindersModule()
```

The Runner scans `modules/*/module.py`, calls `get_module()`, and registers each.
Order of operations at boot:

```
ModuleRegistry.discover()            # import modules, collect Module objects
  → for each: registry.add(module)
ServiceRegistry.start_all(ctx)       # module.start(ctx) in dependency order
ToolRouter.build()                   # gather module.tools() → one tool array
MainWindow.mount_tabs()              # module.tab() → tabs (in configured order)
SettingsTab.mount()                  # module.settings_schema()/settings_widget()
Bus wiring                           # module.subscribe(bus)
```

**Dependency order** is declared, not discovered: a small `requires: list[str]`
on each module (e.g. `terminal` and `timeline` before `reminders`? usually none).
Voice starts first so `ctx.speak` is available to others.

---

## 3. Independent upgradeability — the rules

1. **No cross-module imports.** Modules talk via `ctx.bus` events and via the
   orchestrator's tool calls, never by `import modules.other`. This is the
   linchpin — it's what lets you rewrite `timeline` without touching `voice`.
2. **Stable tool names.** A module may change its internals freely as long as its
   published tool `name`s + schemas stay compatible (or bump `version` and update
   the capability prompt). The orchestrator only knows tools, not implementations.
3. **Own your data.** Each module owns its tables/namespace; other modules read
   through **tools/events**, not by querying foreign tables directly.
4. **Degrade gracefully.** If a module fails to `start()`, the Runner logs it and
   continues; its tools simply aren't offered that session (mirrors how timeline
   already continues if the browser API fails to start).
5. **UI is optional.** A module with no `tab()`/`settings_widget()` still
   contributes tools and services. A "web_fetch" module might be tools-only.

---

## 4. Worked example — the Reminders module (net-new)

```python
class RemindersModule(Module):
    id, name, version = "reminders", "Reminders", "0.1.0"

    def start(self, ctx):
        self.ctx = ctx
        self.store = ReminderStore(ctx.db)
        self.scheduler = ReminderScheduler(self.store, on_due=self._fire)
        self.scheduler.start()

    def stop(self):
        self.scheduler.stop()

    def tools(self):
        return [
            Tool(spec=SET_REMINDER_SPEC,   handler=self.set_reminder,   risk="safe_action"),
            Tool(spec=LIST_REMINDERS_SPEC, handler=self.list_reminders, risk="read_only"),
            Tool(spec=CANCEL_REMINDER_SPEC,handler=self.cancel_reminder,risk="safe_action"),
        ]

    def settings_schema(self):
        return [
            SettingField("popup",  "Show popup when due", "bool", True),
            SettingField("speak",  "Speak reminders",     "bool", True),
            SettingField("snooze", "Default snooze (min)","int",  5),
        ]

    def set_reminder(self, text: str, when: str) -> dict:
        fire_at = parse_datetime(when)          # dateparser NL → datetime
        rid = self.store.add(text, fire_at, source="voice")
        return {"ok": True, "id": rid, "fire_at": fire_at.isoformat()}

    def _fire(self, reminder):
        self.ctx.bus.publish("reminder.due", reminder)   # ui popup + TTS subscribe
        if self.ctx.config.get("speak"):
            self.ctx.speak(f"Reminder: {reminder.text}")
```

That's a full module: three tools the LLM can call, three settings that appear in
Tab 5, a background scheduler, and a `reminder.due` event the UI turns into a
popup — with **zero** edits to any other module.

---

## 5. Mapping existing modules onto the contract

| Module | `start()` boots | `tools()` | `tab()` | Notes |
|--------|-----------------|-----------|---------|-------|
| **voice** | STT/TTS engines, wake listener | — (provides `ctx.speak`) | contributes to Tab 1 | starts first |
| **terminal** | persistent PowerShell `QProcess` | `run_powershell` | Tab 3 | permission risk from safety.py |
| **timeline** | capture thread, browser API, file scan | `recall_search`, `recall_open`, `list_recent_files` | Tab 2 | engine unchanged, UI ported |
| **browser** | (uses timeline's API/DB) | `browser_recall`, `open_last_page` | — | thin reader over `browser_visits` |
| **reminders** | scheduler thread | `set/list/cancel_reminder` | (optional list view) | net-new |
| **power** | — | `get_power_status`, `sleep/shutdown/lock` | — | net-new, small |
| **dashboard** | — | — | Tab (coming soon) | stub |

---

## 6. Adding a future module (the recipe the user asked for)

To add e.g. a **Browser Controller** or **Web Fetch** later:

1. `mkdir modules/webfetch/` and add `module.py` with `get_module()`.
2. Implement `Module`: give it a `tools()` list (e.g. `fetch_url(url)` →
   returns extracted text) with a `risk` tag.
3. (Optional) add `settings_schema()` and/or a `tab()`.
4. Restart. The Runner discovers it, the orchestrator gains the new tool, the
   capability prompt is regenerated, and Settings shows its section.

No other file changes. That is the definition of "upgradable per module".

---

## 7. Versioning & compatibility

- Each module carries `version`. The kernel records `(id, version)` at boot in the
  `event_log` so the Logs tab shows what shipped.
- The kernel declares a `CONTRACT_VERSION`; a module may declare
  `min_contract = "1.0"`. On mismatch the Runner refuses to load that one module
  (and logs why) instead of crashing the app.
- Tool schema changes are the real compatibility surface — treat a tool's
  `name` + required params as its public API.
