"""
Telemetry → memory signal.

Turns a raw solve attempt (how long to understand, how long to write, attempts,
hints, verdict) into two derived numbers the memory model consumes:

  - recall_strength      in [0, 1]  — how strongly this solve demonstrates recall
  - perceived_difficulty in [1, 10] — how hard this problem was *for this user*

Everything is judged relative to the user's OWN rolling baselines for that
difficulty, so "slow" means slow *for them*. On cold start (no baseline yet)
we fall back to global defaults so the numbers are still sensible.
"""
import math
from typing import Dict, Any, Optional, Tuple

# Global priors used until a user has enough of their own data (seconds).
DEFAULT_BASELINES: Dict[str, Dict[str, float]] = {
    "Easy":   {"understand_mean": 90.0,  "understand_std": 60.0,  "write_mean": 240.0, "write_std": 150.0},
    "Medium": {"understand_mean": 240.0, "understand_std": 150.0, "write_mean": 480.0, "write_std": 300.0},
    "Hard":   {"understand_mean": 480.0, "understand_std": 300.0, "write_mean": 900.0, "write_std": 600.0},
}

# Weights for the recall-strength blend.
_A_UNDERSTAND = 0.7
_B_WRITE = 0.5
_ATTEMPT_PENALTY = 0.6   # per extra submission beyond the first
_HINT_PENALTY = 0.8      # per hint used
_FAIL_PENALTY = 2.0      # applied when the attempt was not accepted

MIN_BASELINE_N = 3       # need this many samples before trusting personal baselines


def sigmoid(x: float) -> float:
    # Clamp to avoid overflow on extreme inputs.
    x = max(-30.0, min(30.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def normalize_difficulty(difficulty: Optional[str]) -> str:
    """Maps a platform difficulty (LeetCode label or Codeforces numeric rating) to Easy/Medium/Hard."""
    if not difficulty:
        return "Medium"
    d = str(difficulty).strip()
    if d in ("Easy", "Medium", "Hard"):
        return d
    # Codeforces numeric rating
    try:
        rating = int(float(d))
        if rating < 1200:
            return "Easy"
        if rating < 1700:
            return "Medium"
        return "Hard"
    except (ValueError, TypeError):
        return "Medium"


def _baseline_for(speed_baselines: Dict[str, Any], difficulty: str) -> Dict[str, float]:
    """Returns the user's baseline for a difficulty, falling back to global defaults if too little data."""
    default = DEFAULT_BASELINES.get(difficulty, DEFAULT_BASELINES["Medium"])
    personal = speed_baselines.get(difficulty) if speed_baselines else None
    if not personal or personal.get("n", 0) < MIN_BASELINE_N:
        return default
    # Guard against degenerate zero std.
    return {
        "understand_mean": personal.get("understand_mean", default["understand_mean"]),
        "understand_std": max(1.0, personal.get("understand_std", default["understand_std"])),
        "write_mean": personal.get("write_mean", default["write_mean"]),
        "write_std": max(1.0, personal.get("write_std", default["write_std"])),
    }


def derive_signals(
    speed_baselines: Dict[str, Any],
    difficulty: Optional[str],
    time_to_understand_s: Optional[int],
    time_to_write_s: Optional[int],
    num_submissions: int = 1,
    hints_used: int = 0,
    verdict: str = "Accepted",
) -> Tuple[float, float]:
    """
    Returns (recall_strength, perceived_difficulty).

    Faster-than-baseline, first-try, no-hint solves score high recall / low
    perceived difficulty. Missing timing (e.g. API backfill) simply drops that
    term and leans on attempts/verdict.
    """
    diff = normalize_difficulty(difficulty)
    base = _baseline_for(speed_baselines, diff)

    z_terms = []
    if time_to_understand_s is not None:
        z_u = (base["understand_mean"] - time_to_understand_s) / base["understand_std"]
        z_terms.append(_A_UNDERSTAND * z_u)
    if time_to_write_s is not None:
        z_w = (base["write_mean"] - time_to_write_s) / base["write_std"]
        z_terms.append(_B_WRITE * z_w)

    speed_signal = sum(z_terms)
    attempt_penalty = _ATTEMPT_PENALTY * max(0, num_submissions - 1)
    hint_penalty = _HINT_PENALTY * max(0, hints_used)
    fail_penalty = _FAIL_PENALTY if verdict.strip().lower() not in ("accepted", "ok") else 0.0

    raw = speed_signal - attempt_penalty - hint_penalty - fail_penalty
    recall_strength = sigmoid(raw)

    # perceived difficulty: higher when the user struggled (slow / many attempts / hints).
    # Normalize the two z-terms back out of their weights for an unbiased struggle measure.
    z_mean = (speed_signal / max(1, len(z_terms))) if z_terms else 0.0
    struggle = -z_mean + attempt_penalty + hint_penalty + (1.0 if fail_penalty else 0.0)
    perceived_difficulty = max(1.0, min(10.0, 5.0 + 1.5 * struggle))

    return round(recall_strength, 4), round(perceived_difficulty, 4)


def update_speed_baselines(
    speed_baselines: Dict[str, Any],
    difficulty: Optional[str],
    time_to_understand_s: Optional[int],
    time_to_write_s: Optional[int],
) -> Dict[str, Any]:
    """
    Updates the user's per-difficulty running mean/std with this solve's timings
    (Welford's online algorithm). Returns a new dict; missing timings are skipped.
    """
    diff = normalize_difficulty(difficulty)
    updated = dict(speed_baselines) if speed_baselines else {}
    default = DEFAULT_BASELINES.get(diff, DEFAULT_BASELINES["Medium"])
    entry = dict(updated.get(diff) or {
        "understand_mean": default["understand_mean"], "understand_m2": 0.0,
        "write_mean": default["write_mean"], "write_m2": 0.0, "n": 0,
    })

    n = entry.get("n", 0)
    # Welford requires a fresh count for the paired update; both timings advance n together
    # only when present. To keep it simple we advance n once per attempt that has any timing.
    if time_to_understand_s is None and time_to_write_s is None:
        return updated

    n += 1
    if time_to_understand_s is not None:
        mean = entry["understand_mean"]
        delta = time_to_understand_s - mean
        mean += delta / n
        entry["understand_m2"] = entry.get("understand_m2", 0.0) + delta * (time_to_understand_s - mean)
        entry["understand_mean"] = mean
    if time_to_write_s is not None:
        mean = entry["write_mean"]
        delta = time_to_write_s - mean
        mean += delta / n
        entry["write_m2"] = entry.get("write_m2", 0.0) + delta * (time_to_write_s - mean)
        entry["write_mean"] = mean
    entry["n"] = n

    # Expose std for convenience (population std; guarded for n<2).
    if n >= 2:
        entry["understand_std"] = math.sqrt(entry.get("understand_m2", 0.0) / n) or default["understand_std"]
        entry["write_std"] = math.sqrt(entry.get("write_m2", 0.0) / n) or default["write_std"]
    else:
        entry["understand_std"] = default["understand_std"]
        entry["write_std"] = default["write_std"]

    updated[diff] = entry
    return updated
