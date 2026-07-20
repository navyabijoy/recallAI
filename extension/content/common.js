/*
 * Shared telemetry tracker used by the LeetCode and Codeforces content scripts.
 *
 * It's a small per-problem state machine:
 *   openProblem(meta)   -> t0, remembers which problem you're on
 *   markFirstKeystroke()-> t1 (understand = t1 - t0), fires once per problem
 *   recordSubmit(verdict) -> t2 (write = t2 - t1) + attempts, then posts telemetry
 *
 * Time spent with the tab hidden is subtracted so "understand time" isn't
 * inflated by you walking away. Everything is capped to a sane maximum.
 */
(function () {
  const MAX_SECONDS = 3600; // cap any single interval at 60 min
  const ns = (window.__recallai = window.__recallai || {});

  function now() {
    return Date.now();
  }

  class Tracker {
    constructor() {
      this.reset();
      this._hiddenSince = document.hidden ? now() : null;
      this._hiddenAccum = 0; // ms hidden since the current interval start
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          this._hiddenSince = now();
        } else if (this._hiddenSince) {
          this._hiddenAccum += now() - this._hiddenSince;
          this._hiddenSince = null;
        }
      });
    }

    reset() {
      this.key = null;
      this.meta = null;
      this.openedAt = null;
      this.firstKeystrokeAt = null;
      this.submissions = 0;
      this._hiddenAccum = 0;
      this._hiddenSince = document.hidden ? now() : null;
    }

    _activeSeconds(fromMs, toMs) {
      let hidden = this._hiddenAccum;
      if (this._hiddenSince) hidden += now() - this._hiddenSince; // still hidden right now
      const raw = Math.max(0, (toMs - fromMs - hidden) / 1000);
      return Math.min(MAX_SECONDS, Math.round(raw));
    }

    openProblem(key, meta) {
      if (this.key === key) return; // already tracking this problem
      this.reset();
      this.key = key;
      this.meta = meta;
      this.openedAt = now();
      console.debug("[RecallAI] tracking", key, meta);
    }

    updateMeta(meta) {
      if (this.meta) this.meta = Object.assign({}, this.meta, meta);
    }

    markFirstKeystroke() {
      if (!this.openedAt || this.firstKeystrokeAt) return;
      this.firstKeystrokeAt = now();
      console.debug("[RecallAI] first keystroke");
    }

    recordSubmit(verdict) {
      if (!this.openedAt || !this.meta) return;
      this.submissions += 1;
      const submittedAt = now();
      // If they never triggered a keystroke listener (e.g. pasted), assume write started at open.
      const firstKeystrokeAt = this.firstKeystrokeAt || this.openedAt;

      const payload = {
        platform: this.meta.platform,
        platform_problem_id: this.meta.platform_problem_id,
        title: this.meta.title || null,
        url: this.meta.url || location.href,
        difficulty: this.meta.difficulty || null,
        topic_tags: this.meta.topic_tags || [],
        opened_at: new Date(this.openedAt).toISOString(),
        first_keystroke_at: new Date(firstKeystrokeAt).toISOString(),
        submitted_at: new Date(submittedAt).toISOString(),
        time_to_understand_s: this._activeSeconds(this.openedAt, firstKeystrokeAt),
        time_to_write_s: this._activeSeconds(firstKeystrokeAt, submittedAt),
        num_submissions: this.submissions,
        hints_used: this.meta.hints_used || 0,
        verdict: verdict || "Accepted",
        source: "extension",
      };
      ns.send(payload);
    }
  }

  ns.Tracker = Tracker;

  // Route telemetry through the background worker (avoids page CORS; keeps the key out of the page).
  ns.send = function (payload) {
    try {
      chrome.runtime.sendMessage({ type: "telemetry", payload }, (resp) => {
        if (chrome.runtime.lastError) {
          console.warn("[RecallAI] send failed:", chrome.runtime.lastError.message);
        } else {
          console.debug("[RecallAI] telemetry sent:", resp);
        }
      });
    } catch (e) {
      console.warn("[RecallAI] send error", e);
    }
  };

  // Watches for SPA URL changes (both platforms navigate without full reloads).
  ns.onUrlChange = function (cb) {
    let last = location.href;
    const check = () => {
      if (location.href !== last) {
        last = location.href;
        cb(location.href);
      }
    };
    setInterval(check, 800);
    window.addEventListener("popstate", check);
    cb(location.href); // fire once on load
  };
})();
