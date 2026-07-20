/*
 * Background service worker.
 *
 * Content scripts hand it a telemetry payload; it attaches the user's API key
 * and POSTs to the RecallAI backend. Running the fetch here (with host
 * permissions) sidesteps page CORS and keeps the API key out of the page.
 */
const DEFAULT_BACKEND = "http://localhost:8000";

async function getConfig() {
  const { apiKey, backendUrl } = await chrome.storage.sync.get(["apiKey", "backendUrl"]);
  return { apiKey, backendUrl: backendUrl || DEFAULT_BACKEND };
}

async function postTelemetry(payload) {
  const { apiKey, backendUrl } = await getConfig();
  if (!apiKey) {
    return { ok: false, error: "No API key set. Open the RecallAI popup to configure it." };
  }
  try {
    const res = await fetch(`${backendUrl}/api/telemetry/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    const status = { ok: res.ok, code: res.status, body, at: Date.now(), problem: payload.title };
    await chrome.storage.local.set({ lastStatus: status });
    return status;
  } catch (e) {
    const status = { ok: false, error: String(e), at: Date.now() };
    await chrome.storage.local.set({ lastStatus: status });
    return status;
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "telemetry") {
    postTelemetry(msg.payload).then(sendResponse);
    return true; // async response
  }
  if (msg && msg.type === "getLastStatus") {
    chrome.storage.local.get(["lastStatus"]).then(({ lastStatus }) => sendResponse(lastStatus || null));
    return true;
  }
});
