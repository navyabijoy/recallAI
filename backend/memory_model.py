"""
Personalized memory model.

The forgetting-curve backbone is the same shape as FSRS, but the two parameters
that describe *how a given person's memory behaves* are fit from their own solve
telemetry instead of being global constants:

  - decay_exponent (w): how fast this user forgets      R(t) = (1 + t/(9S))^(-w)
  - stability_growth (g): how much a good solve cements a topic

A solve no longer carries a manual GOOD/HARD grade — it carries a continuous
`recall_strength` derived in telemetry.py, and the model updates stability and
difficulty from that.
"""
from datetime import datetime, timezone
from typing import List, Tuple, Optional

# Cold-start priors (chosen so a brand-new user behaves like textbook FSRS).
DEFAULT_DECAY_EXPONENT = 0.5
DEFAULT_STABILITY_GROWTH = 0.15
MIN_ATTEMPTS_TO_FIT = 8          # don't personalize until we've seen this many revisits

_STABILITY_MIN = 0.1
_STABILITY_MAX = 3650.0          # 10 years


def _elapsed_days(last_review: datetime, current_time: Optional[datetime]) -> float:
    if current_time is None:
        current_time = datetime.utcnow()
    if last_review.tzinfo is not None:
        last_review = last_review.astimezone(timezone.utc).replace(tzinfo=None)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)
    return max(0.0, (current_time - last_review).total_seconds() / 86400.0)


def predict_retrievability(
    stability: float,
    last_review: datetime,
    decay_exponent: float = DEFAULT_DECAY_EXPONENT,
    current_time: Optional[datetime] = None,
) -> float:
    """R = (1 + t/(9S))^(-w). With w=0.5 this is exactly fsrs.calculate_retrievability."""
    t = _elapsed_days(last_review, current_time)
    s = stability if stability > 0 else 0.1
    r = (1.0 + t / (9.0 * s)) ** (-max(0.01, decay_exponent))
    return min(1.0, max(0.0, r))


def update_stability(
    stability: float,
    recall_strength: float,
    perceived_difficulty: float,
    growth: float = DEFAULT_STABILITY_GROWTH,
    confidence_weight: float = 1.0,
) -> float:
    """
    Continuous stability update driven by recall_strength (in [0,1]).

    recall_strength > 0.5 (recalled well)  -> stability grows, harder problems grow slower.
    recall_strength < 0.5 (struggled)      -> stability shrinks toward a fraction of itself.
    The 0.5 midpoint is the no-op boundary, so updates are smooth.
    """
    centered = recall_strength - 0.5
    if centered >= 0:
        difficulty_factor = max(1.0, perceived_difficulty) ** -0.2
        growth_factor = 2.0 * growth * centered * difficulty_factor * confidence_weight
        new_stability = stability * (1.0 + growth_factor)
    else:
        # centered in [-0.5, 0): decay factor in [0.5, 1.0), softened by low confidence.
        decay = 1.0 + centered * confidence_weight
        new_stability = stability * max(0.25, decay)
    return round(max(_STABILITY_MIN, min(_STABILITY_MAX, new_stability)), 4)


def update_difficulty(
    difficulty: float,
    perceived_difficulty: float,
    confidence_weight: float = 1.0,
) -> float:
    """Exponentially-smoothed pull of the stored difficulty toward this solve's perceived difficulty."""
    alpha = 0.3 * confidence_weight
    new_d = difficulty + alpha * (perceived_difficulty - difficulty)
    return round(max(1.0, min(10.0, new_d)), 4)


def fit_decay_exponent(
    samples: List[Tuple[float, float, float]],
    current: float = DEFAULT_DECAY_EXPONENT,
) -> float:
    """
    Fit the personal forgetting exponent w to observed revisit data.

    Each sample is (elapsed_days, stability_at_review, observed_recall_strength):
    at a revisit we had predicted R_w(elapsed, S); the user actually demonstrated
    `observed_recall_strength`. Pick the w on a grid that minimizes squared error.
    Returns the current value unchanged until enough samples exist.
    """
    if len(samples) < MIN_ATTEMPTS_TO_FIT:
        return current

    def mse(w: float) -> float:
        total = 0.0
        for elapsed, stability, observed in samples:
            s = stability if stability > 0 else 0.1
            pred = (1.0 + elapsed / (9.0 * s)) ** (-max(0.01, w))
            total += (pred - observed) ** 2
        return total / len(samples)

    grid = [0.05 * i for i in range(1, 31)]  # 0.05 .. 1.50
    best_w = min(grid, key=mse)
    # Blend toward the fitted value so a single batch can't swing it wildly.
    return round(0.5 * current + 0.5 * best_w, 4)


def revision_priority(
    forgetting_risk: float,
    importance: float = 1.0,
    deadline_urgency: float = 1.0,
) -> float:
    """priority = forgetting_risk * importance * deadline_urgency. Higher = revise sooner."""
    return round(max(0.0, forgetting_risk) * max(0.0, importance) * max(0.0, deadline_urgency), 6)


def prerequisite_boost(base_importance: float, weak_dependents: int) -> float:
    """
    Bumps a topic's importance when downstream topics that depend on it are weak —
    shoring up a shaky foundation pays off across everything built on it.
    """
    return round(base_importance * (1.0 + 0.25 * max(0, weak_dependents)), 4)
