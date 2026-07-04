/*
 * Activity Recall Connector - background service worker (MV3).
 *
 * Tracks the currently-active tab and, when the user switches away from it
 * (tab switch, navigation, tab close, window blur), reports a "visit" with the
 * time the tab became active and the time it was left. Visits are POSTed to the
 * local app at http://127.0.0.1:8123 with a shared bearer token.
 *
 * Nothing leaves the machine: the endpoint is localhost only.
 */

const API_BASE = "http://127.0.0.1:8123";
const DEFAULT_BROWSER = detectBrowser();
const MIN_VISIT_MS = 1500; // ignore quick fly-through tabs

// The visit currently being timed: { tabId, url, title, activatedAt }
let active = null;
const pendingQueue = [];

function detectBrowser() {
  const ua = navigator.userAgent || "";
  if (ua.includes("Edg/")) return "edge";
  if (ua.includes("OPR/")) return "opera";
  if (ua.includes("Brave")) return "brave";
  return "chrome";
}

function isTrackableUrl(url) {
  if (!url) return false;
  return url.startsWith("http://") || url.startsWith("https://");
}

async function getToken() {
  const { recallToken } = await chrome.storage.local.get("recallToken");
  return recallToken || "";
}

async function send(visit) {
  const token = await getToken();
  if (!token) {
    // No token configured yet; queue so we can flush after pairing.
    pendingQueue.push(visit);
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/visit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Recall-Token": token,
      },
      body: JSON.stringify(visit),
    });
    if (!res.ok) {
      console.warn("Recall: visit rejected", res.status);
    }
  } catch (e) {
    // App probably not running; drop silently (queue would grow unbounded).
    console.debug("Recall: app unreachable", e.message);
  }
}

function closeActive(closedAt = Date.now()) {
  if (!active) return;
  const duration = closedAt - active.activatedAt;
  const v = active;
  active = null;
  if (!isTrackableUrl(v.url)) return;
  if (duration < MIN_VISIT_MS) return;
  send({
    url: v.url,
    title: v.title || "",
    browser: DEFAULT_BROWSER,
    activated: v.activatedAt,
    closed: closedAt,
  });
}

function startActive(tab) {
  if (!tab || !isTrackableUrl(tab.url)) {
    active = null;
    return;
  }
  active = {
    tabId: tab.id,
    url: tab.url,
    title: tab.title || "",
    activatedAt: Date.now(),
  };
}

async function switchToTab(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (active && active.tabId === tabId && active.url === tab.url) {
      // Same page still active; just refresh the title.
      active.title = tab.title || active.title;
      return;
    }
    closeActive();
    startActive(tab);
  } catch (e) {
    closeActive();
  }
}

// --- Event wiring -----------------------------------------------------------

chrome.tabs.onActivated.addListener(({ tabId }) => switchToTab(tabId));

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!tab.active) return;
  // Navigation within the active tab: close previous, start new page.
  if (changeInfo.url) {
    closeActive();
    startActive(tab);
  } else if (changeInfo.title && active && active.tabId === tabId) {
    active.title = changeInfo.title;
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (active && active.tabId === tabId) closeActive();
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    // Browser lost focus.
    closeActive();
    return;
  }
  try {
    const [tab] = await chrome.tabs.query({ active: true, windowId });
    if (tab) await switchToTab(tab.id);
  } catch (e) {
    /* ignore */
  }
});

// Flush any queued visits once a token is set.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.recallToken && changes.recallToken.newValue) {
    const queued = pendingQueue.splice(0, pendingQueue.length);
    queued.forEach(send);
  }
});

// Periodically flush the currently-open tab so long reads are captured even
// without a switch (heartbeat every 2 minutes).
chrome.alarms.create("heartbeat", { periodInMinutes: 2 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "heartbeat" && active) {
    const now = Date.now();
    // Record the elapsed chunk and restart the timer for the same page.
    const snapshot = { ...active };
    closeActive(now);
    startActive({
      id: snapshot.tabId,
      url: snapshot.url,
      title: snapshot.title,
    });
  }
});
