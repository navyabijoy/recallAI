/*
 * Background service worker.
 *
 * Content scripts hand it a telemetry payload; it attaches the user's API key
 * and POSTs to the RecallAI backend. Running the fetch here (with host
 * permissions) sidesteps page CORS and keeps the API key out of the page.
 *
 * MV3 service workers get killed after ~30s idle, so nothing here relies on
 * in-memory state surviving between events — payloads that fail to send are
 * queued in chrome.storage.local and retried with backoff via chrome.alarms,
 * which wakes the worker back up even after it's been killed. Retries are
 * safe because the backend's client_event_id dedup makes re-sending the same
 * payload a no-op if the original request actually landed.
 */
const DEFAULT_BACKEND = "http://localhost:8000";
const OUTBOX_ALARM = "recallai-outbox-flush";
const MAX_ATTEMPTS = 8;
const MAX_BACKOFF_MS = 30 * 60 * 1000; // 30 min

async function getConfig() {
  const { apiKey, backendUrl } = await chrome.storage.sync.get(["apiKey", "backendUrl"]);
  return { apiKey, backendUrl: backendUrl || DEFAULT_BACKEND };
}

async function getOutbox() {
  const { outbox } = await chrome.storage.local.get(["outbox"]);
  return outbox || [];
}

async function setOutbox(outbox) {
  await chrome.storage.local.set({ outbox });
}

function backoffDelayMs(attempts) {
  return Math.min(MAX_BACKOFF_MS, 5000 * Math.pow(2, attempts));
}

// Sends once. `retryable` distinguishes "worth queuing" (offline, backend
// down/5xx) from "will never succeed" (missing API key, 4xx like bad payload).
async function sendOnce(payload) {
  const { apiKey, backendUrl } = await getConfig();
  if (!apiKey) {
    return { ok: false, retryable: false, error: "No API key set. Open the RecallAI popup to configure it." };
  }
  try {
    const res = await fetch(`${backendUrl}/api/telemetry/solve`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify(payload),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok && res.status >= 500) {
      return { ok: false, retryable: true, code: res.status, body };
    }
    return { ok: res.ok, retryable: false, code: res.status, body };
  } catch (e) {
    // Network error (offline, backend unreachable) — worth retrying.
    return { ok: false, retryable: true, error: String(e) };
  }
}

async function enqueueOutbox(payload) {
  const outbox = await getOutbox();
  const key = payload.client_event_id;
  if (key && outbox.some((e) => e.payload.client_event_id === key)) return; // already queued
  outbox.push({ payload, attempts: 0, nextRetryAt: Date.now() + backoffDelayMs(0) });
  await setOutbox(outbox);
  scheduleFlush(backoffDelayMs(0));
}

function scheduleFlush(delayMs) {
  chrome.alarms.create(OUTBOX_ALARM, { when: Date.now() + delayMs });
}

async function flushOutbox() {
  let outbox = await getOutbox();
  if (!outbox.length) return;

  const remaining = [];
  let earliestRetry = null;
  for (const entry of outbox) {
    if (Date.now() < entry.nextRetryAt) {
      remaining.push(entry);
      earliestRetry = earliestRetry ? Math.min(earliestRetry, entry.nextRetryAt) : entry.nextRetryAt;
      continue;
    }
    const result = await sendOnce(entry.payload);
    if (result.ok) continue; // delivered — drop from outbox

    entry.attempts += 1;
    if (!result.retryable || entry.attempts >= MAX_ATTEMPTS) continue; // give up — drop
    entry.nextRetryAt = Date.now() + backoffDelayMs(entry.attempts);
    remaining.push(entry);
    earliestRetry = earliestRetry ? Math.min(earliestRetry, entry.nextRetryAt) : entry.nextRetryAt;
  }

  await setOutbox(remaining);
  if (earliestRetry) scheduleFlush(Math.max(0, earliestRetry - Date.now()));
}

async function postTelemetry(payload) {
  const result = await sendOnce(payload);
  const status = { ok: result.ok, code: result.code, body: result.body, error: result.error, at: Date.now(), problem: payload.title };
  await chrome.storage.local.set({ lastStatus: status });

  if (!result.ok && result.retryable) {
    await enqueueOutbox(payload);
  }
  return status;
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === OUTBOX_ALARM) flushOutbox();
});

// The worker can be killed and later woken by an unrelated event (e.g. a new
// telemetry message) — drain any pending outbox entries whenever that happens.
flushOutbox();

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
