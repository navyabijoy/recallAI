const $ = (id) => document.getElementById(id);

async function load() {
  const { apiKey, backendUrl } = await chrome.storage.sync.get(["apiKey", "backendUrl"]);
  if (apiKey) $("apiKey").value = apiKey;
  $("backendUrl").value = backendUrl || "http://localhost:8000";
  renderStatus();
}

async function renderStatus() {
  const last = await chrome.runtime.sendMessage({ type: "getLastStatus" });
  const el = $("status");
  if (!last) {
    el.textContent = "No solves sent yet. Solve a problem to test it.";
    el.className = "status";
    return;
  }
  const when = new Date(last.at).toLocaleTimeString();
  if (last.ok) {
    el.className = "status ok";
    el.textContent = `✓ Last sent ${last.problem || "solve"} at ${when}.`;
  } else {
    el.className = "status err";
    el.textContent = `✗ ${last.error || "HTTP " + last.code} (${when})`;
  }
}

$("save").addEventListener("click", async () => {
  await chrome.storage.sync.set({
    apiKey: $("apiKey").value.trim(),
    backendUrl: $("backendUrl").value.trim() || "http://localhost:8000",
  });
  $("status").className = "status ok";
  $("status").textContent = "Saved.";
});

load();
