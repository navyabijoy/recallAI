# RecallAI Telemetry Extension

Captures **how long you take to understand vs. write** each DSA solution on
LeetCode and Codeforces, plus attempts / hints / verdict, and posts it to the
RecallAI backend which feeds your personalized memory model.

## What it measures

Per problem:
- **time_to_understand** = problem open → first keystroke in the editor
- **time_to_write** = first keystroke → accepted submission
- **num_submissions**, **verdict**, and problem metadata (slug, difficulty, tags)

Time spent with the tab hidden is subtracted, and each interval is capped at 60 minutes.

## Setup

1. Run the backend locally (`uvicorn backend.main:app --reload`, default `http://localhost:8000`),
   or point at the deployed Railway backend URL for beta testers.
2. Mint an API key while logged into the web app (`POST /api/me/api-keys`, Bearer JWT auth) —
   easiest via the Settings page in the frontend once it's built.
3. Load the extension: `chrome://extensions` → enable **Developer mode** →
   **Load unpacked** → select this `extension/` folder.
4. Click the RecallAI toolbar icon, paste the **backend URL** and **API key**, Save.
5. Solve a problem. The popup shows the last-sent status.

For beta testers hitting a deployed backend (not localhost), `manifest.json`'s
`host_permissions` must include that origin — it already covers `*.up.railway.app`;
add your custom domain there if you use one, then reload the unpacked extension.

## Architecture

- `content/common.js` — shared per-problem timing state machine + SPA URL watcher.
- `content/leetcode.js` / `content/codeforces.js` — platform DOM scraping (open, keystroke, verdict).
- `background.js` — receives payloads, attaches the API key, POSTs `/api/telemetry/solve`
  (fetching here avoids page CORS and keeps the key out of the page).
- `popup.html/js` — configure backend URL + API key, view last status.

## Known fragility

DOM scraping breaks when the sites change markup. All selectors are grouped in a
`SELECTORS` object at the top of each content script — fix them there. Codeforces
timing is best-effort because reading and submitting happen on different pages.
