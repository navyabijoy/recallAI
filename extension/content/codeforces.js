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
    verdictCell: "td.status-verdict-cell, span.verdict-accepted, span.verdict-rejected",
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

  function startProblem() {
    const pid = problemIdFromUrl();
    if (!pid) return;
    tracker.openProblem("codeforces:" + pid, {
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

  // Read verdicts from the submissions/status table.
  const seen = new WeakSet();
  const observer = new MutationObserver(() => {
    document.querySelectorAll(SELECTORS.verdictCell).forEach((cell) => {
      const txt = (cell.textContent || "").trim();
      if (!txt || seen.has(cell)) return;
      if (/Accepted|Wrong answer|Time limit|Runtime error|Compilation error|Memory limit/i.test(txt)) {
        seen.add(cell);
        const verdict = /Accepted/i.test(txt) ? "Accepted" : txt;
        tracker.recordSubmit(verdict);
      }
    });
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });

  ns.onUrlChange(() => {
    if (/\/problem\//.test(location.pathname)) startProblem();
  });
})();
