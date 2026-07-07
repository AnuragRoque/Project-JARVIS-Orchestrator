# Activity Recall Connector (Chrome / Edge)

Sends the pages you actively view to your **local** Windows Activity Recall app.
Data never leaves your machine — the extension only talks to
`http://127.0.0.1:8123`.

## Install (unpacked)

1. Make sure the desktop app is running (`python main.py`).
2. Open your browser's extensions page:
   - Chrome: `chrome://extensions`
   - Edge:   `edge://extensions`
3. Enable **Developer mode**.
4. Click **Load unpacked** and select this `extension/` folder.
5. Click the extension's icon (or open its **Options**).
6. Paste the **pairing token** shown in the desktop app under
   **Settings → Browser**, then click **Save & Test Connection**.
   You should see “✓ Connected”.

## What it records

For each page you actively view for more than ~1.5s:

- URL, page title, browser, and how long the tab was focused.

It ignores `chrome://`, `edge://`, and other non-http pages, and respects the
app's **Private mode** / **browser tracking** switches.

## How it works

The service worker (`background.js`) times the active tab and posts a "visit"
to the local API when you switch away, navigate, close the tab, or blur the
window. A 2-minute heartbeat captures long reads. Requests carry a bearer token
so only your paired browser can write to the app.
