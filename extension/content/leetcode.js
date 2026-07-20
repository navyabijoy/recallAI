/*
 * LeetCode content script.
 *
 * All DOM-dependent selectors are grouped in SELECTORS so that when LeetCode
 * changes its markup you only have to fix one place (see risks in README).
 */
(function () {
  const ns = window.__recallai;
  const tracker = new ns.Tracker();

  const SELECTORS = {
    // Difficulty pill on the problem page.
    difficulty: [
      'div[class*="text-difficulty-easy"]',
      'div[class*="text-difficulty-medium"]',
      'div[class*="text-difficulty-hard"]',
      'span[class*="text-olive"]', // legacy
    ],
    // Topic tag anchors (visible when the "Topics" section is expanded).
    topicTags: 'a[href^="/tag/"]',
    // Monaco editor hidden input; keystrokes here mean "started writing".
    editorInput: "textarea.inputarea, .monaco-editor textarea",
    // Verdict text container after a submission.
    verdictHosts: '[data-e2e-locator="submission-result"], [data-e2e-locator="console-result"]',
  };

  const VERDICTS = [
    "Accepted", "Wrong Answer", "Time Limit Exceeded",
    "Runtime Error", "Compile Error", "Memory Limit Exceeded",
  ];

  function slugFromUrl() {
    const m = location.pathname.match(/\/problems\/([^/]+)/);
    return m ? m[1] : null;
  }

  function scrapeDifficulty() {
    for (const sel of SELECTORS.difficulty) {
      const el = document.querySelector(sel);
      if (el && el.textContent) {
        const txt = el.textContent.trim();
        if (["Easy", "Medium", "Hard"].includes(txt)) return txt;
        const cls = el.className.toLowerCase();
        if (cls.includes("easy")) return "Easy";
        if (cls.includes("medium")) return "Medium";
        if (cls.includes("hard")) return "Hard";
      }
    }
    return null;
  }

  function scrapeTags() {
    const tags = [];
    document.querySelectorAll(SELECTORS.topicTags).forEach((a) => {
      const m = a.getAttribute("href").match(/\/tag\/([^/]+)/);
      if (m && !tags.includes(m[1])) tags.push(m[1]);
    });
    return tags;
  }

  function scrapeTitle() {
    const slug = slugFromUrl();
    const el = document.querySelector('a[href^="/problems/' + slug + '"]');
    if (el && el.textContent.trim()) return el.textContent.trim();
    return document.title.replace(/ - LeetCode.*/, "").trim() || null;
  }

  function startProblem() {
    const slug = slugFromUrl();
    if (!slug) return;
    tracker.openProblem("leetcode:" + slug, {
      platform: "leetcode",
      platform_problem_id: slug,
      title: scrapeTitle(),
      url: location.href,
      difficulty: scrapeDifficulty(),
      topic_tags: scrapeTags(),
    });
    // Metadata can render slightly after navigation — re-scrape shortly after.
    setTimeout(() => {
      tracker.updateMeta({ difficulty: scrapeDifficulty(), topic_tags: scrapeTags(), title: scrapeTitle() });
    }, 2500);
  }

  // First keystroke inside the code editor.
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t && t.matches && t.matches(SELECTORS.editorInput)) {
      tracker.markFirstKeystroke();
    }
  }, true);

  // Watch for a verdict appearing after submission.
  const seenVerdicts = new WeakSet();
  const observer = new MutationObserver(() => {
    const hosts = document.querySelectorAll(SELECTORS.verdictHosts);
    hosts.forEach((host) => {
      const txt = (host.textContent || "").trim();
      const verdict = VERDICTS.find((v) => txt.includes(v));
      if (verdict && !seenVerdicts.has(host)) {
        seenVerdicts.add(host);
        tracker.recordSubmit(verdict);
      }
    });
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });

  ns.onUrlChange(() => {
    if (location.pathname.includes("/problems/")) startProblem();
  });
})();
