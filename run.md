# Running JARVIS — step by step

The unified app lives in **`jarvis/`**. This is the only thing you launch; it
boots every background service, drops a tray icon + floating orb, and opens into
a 6-tab window. (The three original folders — `jarvis_voice_core/`,
`terminal_access_module/`, `timeline_monitor_module/` — are kept only as the
source of truth; you don't run them anymore.)

---

## 1. Prerequisites

- **Windows 10/11** (uses PowerShell, Windows SAPI voices, Recent-Items recall).
- **Python 3.12** on your PATH. Check:
  ```powershell
  python --version
  ```
- A **microphone** if you want voice (typing works without one).
- An **OpenAI API key** (the brain) and a **Sarvam API key** (speech-to-text).
  Text-to-speech uses the free built-in Windows voices — no key needed.

All commands below are run from the **project root** (the folder that contains
`jarvis/`, this `run.md`, and `README.md`).

---

## 2. Install dependencies

Use a virtual environment (recommended) or your global Python.

```powershell
# from the project root
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell  (use activate.bat for cmd.exe)

pip install -r jarvis\requirements.txt
```

> If PowerShell blocks the activate script, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` and re-open the terminal.

---

## 3. Add your API keys

Open **`jarvis\modules\voice\.env`** and fill in three values:

```env
OPENAI_API_KEY=sk-...your key...
OPENAI_MODEL=gpt-4o-mini
SARVAM_API_KEY=...your Sarvam key...
```

Notes:

- `OPENAI_MODEL` must be a **real** model id (e.g. `gpt-4o-mini`). The orchestrator
  (Tab 1's brain) and the voice chat both use these values.
- Leave `SARVAM_API_KEY` blank if you only want to **type** — voice input needs it.
- The terminal module has its own `jarvis\modules\terminal\.env`; you can leave it
  as-is for now (key centralisation is a later phase).

---

## 4. Run

```powershell
python -m jarvis
```

What happens:

1. A **tray icon** (blue "J") appears — the app now lives there (no taskbar button).
2. A **floating orb / card** appears top-right of your screen.
3. In the background it starts activity capture, the file-recall scan, and the
   local browser API (`127.0.0.1:8123`).

Launching `python -m jarvis` again just re-surfaces the running instance (single
instance).

---

## 5. Using it

**The floating card** (always available):

- **Type** a message and press Enter.
- Tap the **small mic** for one line of speech.
- Tap the **big orb mic** for a hands-free conversation (it listens, answers,
  speaks, keeps listening; tap again to stop).
- **☐ maximise** → opens the full tabbed window.
- **–** collapses to a small orb (tap the orb to expand). **✕** hides it (reopen
  from the tray).
- **Drag** anywhere to move it.

**The tabbed window** (☐ or double-click the tray icon):

- **Voice Chat** — the same conversation as the orb (the controller hub).
- **Activity Timeline** — everything you've used; search it, click a result to reopen.
- **Terminal** — the live PowerShell session (commands JARVIS runs also appear here).
- **Logs / Settings / Dashboard** — placeholders for upcoming phases.

**Try saying / typing:**

| Example                                         | What it does                                           |
| ----------------------------------------------- | ------------------------------------------------------ |
| "What's Apple?"                                 | Answers directly (no tools).                           |
| "What's my computer's name?"                    | Runs a PowerShell command and answers from the output. |
| "What documents did I open in the last 2 days?" | Recalls your activity and lists matches.               |
| "Open the second one."                          | Reopens that recalled item.                            |

**Permission mode** (the 🛡 dropdown in the chat): **Auto / Partial / Manual**.

- *Partial* (default): read-only questions and recall run instantly; a risky
  action (delete, shutdown, stop a process…) triggers a confirmation — JARVIS
  **speaks** "Sir, confirm…?" and shows a dialog. Answer by **voice** ("yes" /
  "no") or by clicking **Allow / Don't Allow**.
- *Manual*: asks before anything that isn't read-only. *Auto*: runs everything.
  Your choice is saved and shared between the orb and the tab.

---

## 6. Optional — Chrome/Edge activity recall

To let JARVIS recall browser pages ("open the Hotstar tab I was on"):

1. In the tabbed window open **Activity Timeline → Settings** and copy the
   **pairing token**.
2. Go to `chrome://extensions` (or `edge://extensions`), enable **Developer mode**,
   click **Load unpacked**, and select **`jarvis\extension`**.
3. Open the extension's options, paste the token, **Save & Test Connection**.

---

## 7. Optional — semantic ("by meaning") recall

```powershell
pip install sentence-transformers faiss-cpu
```

Then enable **semantic indexing** in the Activity Timeline → Settings section.
(The first semantic search downloads a small model and takes ~20s.)

---

## 8. Quitting

- **Right-click the tray icon → Quit** (or the tray menu). This stops all services
  cleanly. Closing the windows only hides them — the app keeps running in the tray.

---

## 9. Troubleshooting

| Symptom                                 | Fix                                                                                          |
| --------------------------------------- | -------------------------------------------------------------------------------------------- |
| "Missing OpenAI/Sarvam API key" in chat | Fill in`jarvis\modules\voice\.env` (step 3), then restart.                                 |
| Chat error mentioning the model         | `OPENAI_MODEL` isn't a valid id — set `gpt-4o-mini`.                                    |
| No voice / mic error                    | Check Windows mic permissions; typing still works. Voice input also needs`SARVAM_API_KEY`. |
| Terminal tab shows nothing              | It starts a PowerShell session on open; type a command and press Enter.                      |
| Nothing in Activity Timeline yet        | Capture records as you use apps — use the PC for a bit, it fills in.                        |
| Want to wipe all recorded activity      | Activity Timeline → Settings →**Clear All History**.                                 |

**Data locations** (delete to reset):

- App data & logs: `%LOCALAPPDATA%\Jarvis\`
- Activity history: `%LOCALAPPDATA%\WindowsActivityRecall\`

---

## 10. For developers

```powershell
# run the moved test suite
python -m pytest jarvis\modules\terminal\tests -q

# headless import/boot sanity (no window)
$env:QT_QPA_PLATFORM = "offscreen"; python -c "import jarvis.runner as r; print('ok')"
```

Architecture and the phase plan: see **`docs\ARCHITECTURE.md`**, **`docs\ROADMAP.md`**,
and current progress in **`docs\STATUS.md`**.
