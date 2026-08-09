/*
 * Codeforces content script.
 *
 * CF splits reading (problem page) from writing (submit page), so timing is
 * best-effort: we start the clock when a problem statement opens, mark the
 * first keystroke in the source textarea, and read the verdict from the
 * status/submissions table. Selectors are grouped for easy repair.
 */
(function () {
  const ns = window.__recallai;
  const tracker = new ns.Tracker();

  const SELECTORS = {
    ratingTag: ".tag-box[title='Difficulty'], span.tag-box", // e.g. "*1500"
    topicTags: "a.tag-box, .roundbox .tag-box",
    sourceTextarea: "textarea#sourceCodeTextarea, textarea[name='source'], .ace_text-input",
    submissionRow: "tr[data-submission-id]",
    verdictCell: "td.status-verdict-cell",
    problemLink: "a[href*='/problem/']",
  };

  // /problemset/problem/1520/D  or  /contest/1520/problem/D
  function problemIdFromUrl() {
    let m = location.pathname.match(/\/problemset\/problem\/(\d+)\/([A-Za-z0-9]+)/);
    if (m) return m[1] + "/" + m[2];
    m = location.pathname.match(/\/contest\/(\d+)\/problem\/([A-Za-z0-9]+)/);
    if (m) return m[1] + "/" + m[2];
    return null;
  }

  function scrapeRating() {
    for (const el of document.querySelectorAll(SELECTORS.ratingTag)) {
      const txt = (el.textContent || "").trim();
      const m = txt.match(/\*?(\d{3,4})/);
      if (m) return m[1]; // numeric CF rating; backend maps it to Easy/Medium/Hard
    }
    return null;
  }

  function scrapeTags() {
    const tags = [];
    document.querySelectorAll(SELECTORS.topicTags).forEach((el) => {
      const txt = (el.textContent || "").trim().replace(/^\*/, "").toLowerCase();
      if (txt && !/^\d+$/.test(txt) && !tags.includes(txt)) tags.push(txt);
    });
    return tags;
  }

  function scrapeTitle() {
    const el = document.querySelector(".problem-statement .title, .header .title");
    return el ? el.textContent.trim() : document.title.replace(/ - Codeforces.*/, "").trim();
  }

  async function startProblem() {
    const pid = problemIdFromUrl();
    if (!pid) return;
    await tracker.openProblem("codeforces:" + pid, {
      platform: "codeforces",
      platform_problem_id: pid,
      title: scrapeTitle(),
      url: location.href,
      difficulty: scrapeRating(),
      topic_tags: scrapeTags(),
    });
  }

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t && t.matches && t.matches(SELECTORS.sourceTextarea)) {
      tracker.markFirstKeystroke();
    }
  }, true);

  // CF submits on a separate page from the problem statement (the tracker's
  // `key` survives the navigation — see startProblem/onUrlChange below), so we
  // read the verdict from "my submissions" pages. We deliberately do NOT watch
  // the general /status or /submissions tables: those list every user's rows,
  // and attributing a stranger's verdict to whatever problem we last opened
  // would silently corrupt telemetry.
  function isMySubmissionsPage() {
    return /\/my(\/|$)/.test(location.pathname) || /\bmy=on\b/.test(location.search);
  }

  function rowProblemId(row) {
    const link = row.querySelector(SELECTORS.problemLink);
    if (!link) return null;
    const href = link.getAttribute("href") || "";
    let m = href.match(/\/problemset\/problem\/(\d+)\/([A-Za-z0-9]+)/);
    if (m) return m[1] + "/" + m[2];
    m = href.match(/\/contest\/(\d+)\/problem\/([A-Za-z0-9]+)/);
    return m ? m[1] + "/" + m[2] : null;
  }

  // CF's submit page is a fresh page load, so this content script's `tracker`
  // starts with no key here — resume whichever tracked problem (if any) has a
  // row on this page from the state common.js persisted on the problem page.
  let resuming = false;
  async function resumeTrackingForSubmissionsPage() {
    if (tracker.key || resuming || !isMySubmissionsPage()) return;
    resuming = true;
    try {
      for (const row of document.querySelectorAll(SELECTORS.submissionRow)) {
        const pid = rowProblemId(row);
        if (!pid) continue;
        const key = "codeforces:" + pid;
        const storageKey = "recallai_track_" + key;
        const stored = await chrome.storage.local.get([storageKey]);
        const saved = stored[storageKey];
        if (saved && saved.savedAt && Date.now() - saved.savedAt < 24 * 60 * 60 * 1000) {
          await tracker.openProblem(key, saved.meta || { platform: "codeforces", platform_problem_id: pid });
          break;
        }
      }
    } finally {
      resuming = false;
    }
  }

  const seenVerdicts = new WeakSet();
  const observer = new MutationObserver(() => {
    if (!isMySubmissionsPage()) return;
    if (!tracker.key) {
      resumeTrackingForSubmissionsPage();
      return;
    }
    const currentPid = tracker.key.slice("codeforces:".length);
    for (const row of document.querySelectorAll(SELECTORS.submissionRow)) {
      if (rowProblemId(row) !== currentPid) continue;
      const cell = row.querySelector(SELECTORS.verdictCell);
      if (!cell) continue;
      const txt = (cell.textContent || "").trim();
      if (!txt || seenVerdicts.has(cell)) continue;
      if (/Accepted|Wrong answer|Time limit|Runtime error|Compilation error|Memory limit/i.test(txt)) {
        seenVerdicts.add(cell);
        const verdict = /Accepted/i.test(txt) ? "Accepted" : txt;
        tracker.recordSubmit(verdict);
      }
      break; // most recent row for this problem only
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  resumeTrackingForSubmissionsPage(); // rows may already be in the DOM before any mutation fires

  ns.onUrlChange(() => {
    if (/\/problem\//.test(location.pathname)) startProblem();
  });
})();
