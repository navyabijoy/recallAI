/*
 * Shared telemetry tracker used by the LeetCode and Codeforces content scripts.
 *
 * It's a small per-problem state machine:
 *   openProblem(meta)   -> t0, remembers which problem you're on (async: may
 *                          resume state persisted from a previous page load)
 *   markFirstKeystroke()-> t1 (understand = t1 - t0), fires once per problem
 *   recordSubmit(verdict) -> only Accepted emits telemetry (write = t2 - t1);
 *                          non-terminal verdicts just bump the attempt count
 *
 * Time spent with the tab hidden is subtracted per-interval (not from a single
 * running total) so understand-time and write-time each only lose the hidden
 * time that actually occurred inside that interval. Everything is capped to a
 * sane maximum.
 *
 * State is persisted to chrome.storage.local (keyed by platform:problem_id) so
 * a reload, browser restart, or a platform that submits on a different page
 * (Codeforces) doesn't fabricate a fresh clock — see codeforces.js.
 */
(function () {
  const MAX_SECONDS = 3600; // cap any single interval at 60 min
  const STATE_TTL_MS = 24 * 60 * 60 * 1000; // abandoned tracking state expires after 24h
  const ns = (window.__recallai = window.__recallai || {});

  function now() {
    return Date.now();
  }

  function storageKey(key) {
    return "recallai_track_" + key;
  }

  function newEventId() {
    return (crypto && crypto.randomUUID) ? crypto.randomUUID() : `${now()}-${Math.random().toString(36).slice(2)}`;
  }

  class Tracker {
    constructor() {
      this.key = null;
      this.meta = null;
      this.openedAt = null;
      this.firstKeystrokeAt = null;
      this.clientEventId = null;
      this.submissions = 0;
      this._hiddenAccum = 0; // ms hidden since openedAt
      this._hiddenAtFirstKeystroke = 0; // snapshot of _hiddenAccum(+live) taken at first keystroke
      this._hiddenSince = document.hidden ? now() : null;

      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          this._hiddenSince = now();
        } else if (this._hiddenSince) {
          this._hiddenAccum += now() - this._hiddenSince;
          this._hiddenSince = null;
        }
        this._persist();
      });
    }

    _currentHiddenTotal() {
      let hidden = this._hiddenAccum;
      if (this._hiddenSince) hidden += now() - this._hiddenSince; // still hidden right now
      return hidden;
    }

    _activeSeconds(fromMs, toMs, hiddenMs) {
      const raw = Math.max(0, (toMs - fromMs - hiddenMs) / 1000);
      return Math.min(MAX_SECONDS, Math.round(raw));
    }

    async _persist() {
      if (!this.key) return;
      try {
        await chrome.storage.local.set({
          [storageKey(this.key)]: {
            openedAt: this.openedAt,
            firstKeystrokeAt: this.firstKeystrokeAt,
            clientEventId: this.clientEventId,
            submissions: this.submissions,
            hiddenAccum: this._hiddenAccum,
            hiddenAtFirstKeystroke: this._hiddenAtFirstKeystroke,
            meta: this.meta,
            savedAt: now(),
          },
        });
      } catch (e) {
        console.warn("[RecallAI] persist failed", e);
      }
    }

    async _clear() {
      if (!this.key) return;
      try {
        await chrome.storage.local.remove(storageKey(this.key));
      } catch (e) {
        console.warn("[RecallAI] clear failed", e);
      }
    }

    _startFresh(meta) {
      this.openedAt = now();
      this.firstKeystrokeAt = null;
      this.clientEventId = newEventId();
      this.submissions = 0;
      this._hiddenAccum = 0;
      this._hiddenAtFirstKeystroke = 0;
      this._hiddenSince = document.hidden ? now() : null;
      this.meta = meta;
    }

    /**
     * Starts (or resumes) tracking `key`. Safe to call repeatedly with the same
     * key — only metadata is refreshed. Resumes persisted state (from a prior
     * page load, or another tab tracking the same problem) if it's still fresh.
     */
    async openProblem(key, meta) {
      if (this.key === key) {
        this.meta = Object.assign({}, this.meta, meta);
        return;
      }
      this.key = key;

      let saved = null;
      try {
        const stored = await chrome.storage.local.get([storageKey(key)]);
        saved = stored[storageKey(key)];
      } catch (e) {
        console.warn("[RecallAI] resume lookup failed", e);
      }

      if (saved && saved.savedAt && now() - saved.savedAt < STATE_TTL_MS) {
        this.openedAt = saved.openedAt;
        this.firstKeystrokeAt = saved.firstKeystrokeAt;
        this.clientEventId = saved.clientEventId || newEventId();
        this.submissions = saved.submissions || 0;
        this._hiddenAccum = saved.hiddenAccum || 0;
        this._hiddenAtFirstKeystroke = saved.hiddenAtFirstKeystroke || 0;
        this._hiddenSince = document.hidden ? now() : null;
        this.meta = Object.assign({}, saved.meta, meta);
        console.debug("[RecallAI] resumed tracking", key);
      } else {
        this._startFresh(meta);
        console.debug("[RecallAI] tracking", key, meta);
      }
      await this._persist();
    }

    updateMeta(meta) {
      if (this.meta) this.meta = Object.assign({}, this.meta, meta);
      this._persist();
    }

    markFirstKeystroke() {
      if (!this.openedAt || this.firstKeystrokeAt) return;
      this.firstKeystrokeAt = now();
      this._hiddenAtFirstKeystroke = this._currentHiddenTotal();
      console.debug("[RecallAI] first keystroke");
      this._persist();
    }

    /**
     * Records a submission verdict. Only a terminal Accepted emits telemetry —
     * intermediate failures just bump `submissions` so the eventual Accepted
     * record reflects how many tries it took, instead of each failure posting
     * its own (mid-solve) row.
     */
    recordSubmit(verdict) {
      if (!this.openedAt || !this.meta) return;
      this.submissions += 1;

      if (verdict !== "Accepted") {
        this._persist();
        return;
      }

      const submittedAt = now();
      const firstKeystrokeAt = this.firstKeystrokeAt || this.openedAt;
      const hiddenAtFirstKeystroke = this.firstKeystrokeAt ? this._hiddenAtFirstKeystroke : 0;
      const totalHiddenNow = this._currentHiddenTotal();

      const payload = {
        client_event_id: this.clientEventId,
        platform: this.meta.platform,
        platform_problem_id: this.meta.platform_problem_id,
        title: this.meta.title || null,
        url: this.meta.url || location.href,
        difficulty: this.meta.difficulty || null,
        topic_tags: this.meta.topic_tags || [],
        opened_at: new Date(this.openedAt).toISOString(),
        first_keystroke_at: new Date(firstKeystrokeAt).toISOString(),
        submitted_at: new Date(submittedAt).toISOString(),
        time_to_understand_s: this._activeSeconds(this.openedAt, firstKeystrokeAt, hiddenAtFirstKeystroke),
        time_to_write_s: this._activeSeconds(firstKeystrokeAt, submittedAt, Math.max(0, totalHiddenNow - hiddenAtFirstKeystroke)),
        num_submissions: this.submissions,
        hints_used: this.meta.hints_used || 0,
        verdict: "Accepted",
        source: "extension",
      };
      ns.send(payload);
      this._clear();
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
