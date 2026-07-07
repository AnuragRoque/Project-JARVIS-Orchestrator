const API_BASE = "http://127.0.0.1:8123";
const tokenInput = document.getElementById("token");
const statusEl = document.getElementById("status");

chrome.storage.local.get("recallToken").then(({ recallToken }) => {
  if (recallToken) tokenInput.value = recallToken;
});

function setStatus(msg, ok) {
  statusEl.textContent = msg;
  statusEl.className = "status " + (ok ? "ok" : "err");
}

document.getElementById("save").addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  if (!token) {
    setStatus("Please paste a token.", false);
    return;
  }
  await chrome.storage.local.set({ recallToken: token });
  // Test the connection with a status call.
  try {
    const res = await fetch(`${API_BASE}/api/status`, {
      headers: { "X-Recall-Token": token },
    });
    if (res.ok) {
      const data = await res.json();
      setStatus(
        data.browser_tracking_enabled
          ? "✓ Connected. Browser tracking is on."
          : "✓ Connected, but browser tracking is disabled in the app.",
        true
      );
    } else if (res.status === 401) {
      setStatus("✗ Token rejected. Check the token and try again.", false);
    } else {
      setStatus(`✗ Unexpected response: ${res.status}`, false);
    }
  } catch (e) {
    setStatus("✗ Could not reach the app. Is it running?", false);
  }
});
