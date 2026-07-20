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

1. Run the backend (`uvicorn backend.main:app --reload`, default `http://localhost:8000`).
2. Mint an API key for your user:
   ```
   curl -s -X POST http://localhost:8000/api/users/<USER_ID>/api-keys \
        -H 'Content-Type: application/json' -d '{"label":"my-browser"}'
   ```
   (`GET /api/users/current` returns the demo user id.)
3. Load the extension: `chrome://extensions` → enable **Developer mode** →
   **Load unpacked** → select this `extension/` folder.
4. Click the RecallAI toolbar icon, paste the **backend URL** and **API key**, Save.
5. Solve a problem. The popup shows the last-sent status.

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
