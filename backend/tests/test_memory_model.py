"""
Tests for the personalized, telemetry-driven memory model:
recall-strength derivation, retention decay, per-user parameter fitting,
stability/difficulty updates, and revision prioritization.
"""
import math
from datetime import datetime, timedelta

from backend.telemetry import (
    derive_signals, update_speed_baselines, normalize_difficulty, sigmoid,
)
from backend.memory_model import (
    predict_retrievability, update_stability, update_difficulty,
    fit_decay_exponent, revision_priority, prerequisite_boost,
    DEFAULT_DECAY_EXPONENT,
)


# --- recall strength ---

def test_recall_strength_fast_beats_slow():
    """A fast, first-try, no-hint solve should score much higher recall than a slow, hinted one."""
    strong, _ = derive_signals({}, "Medium", time_to_understand_s=60, time_to_write_s=120,
                               num_submissions=1, hints_used=0, verdict="Accepted")
    weak, _ = derive_signals({}, "Medium", time_to_understand_s=600, time_to_write_s=1200,
                             num_submissions=4, hints_used=3, verdict="Accepted")
    assert strong > weak
    assert 0.0 <= weak <= strong <= 1.0

def test_recall_strength_penalizes_attempts_and_hints():
    base, _ = derive_signals({}, "Medium", 200, 400, num_submissions=1, hints_used=0)
    many, _ = derive_signals({}, "Medium", 200, 400, num_submissions=5, hints_used=0)
    hinted, _ = derive_signals({}, "Medium", 200, 400, num_submissions=1, hints_used=3)
    assert many < base
    assert hinted < base

def test_recall_strength_non_accepted_is_low():
    ok, _ = derive_signals({}, "Medium", 120, 240, verdict="Accepted")
    fail, _ = derive_signals({}, "Medium", 120, 240, verdict="Wrong Answer")
    assert fail < ok

def test_recall_strength_handles_missing_timing():
    # API backfill: no understand/write time — should still return a valid strength.
    val, diff = derive_signals({}, "Medium", None, None, num_submissions=2, verdict="Accepted")
    assert 0.0 <= val <= 1.0
    assert 1.0 <= diff <= 10.0

def test_perceived_difficulty_tracks_struggle():
    _, easy_diff = derive_signals({}, "Medium", 60, 120, num_submissions=1, hints_used=0)
    _, hard_diff = derive_signals({}, "Medium", 600, 1200, num_submissions=4, hints_used=3)
    assert hard_diff > easy_diff
    assert 1.0 <= easy_diff <= 10.0 and 1.0 <= hard_diff <= 10.0

def test_sigmoid_bounds():
    assert 0.0 < sigmoid(-100) < sigmoid(0) < sigmoid(100) < 1.0
    assert abs(sigmoid(0) - 0.5) < 1e-9


# --- difficulty normalization ---

def test_normalize_difficulty_labels_and_ratings():
    assert normalize_difficulty("Easy") == "Easy"
    assert normalize_difficulty("Hard") == "Hard"
    assert normalize_difficulty("900") == "Easy"      # Codeforces rating
    assert normalize_difficulty("1500") == "Medium"
    assert normalize_difficulty("2100") == "Hard"
    assert normalize_difficulty(None) == "Medium"


# --- speed baselines ---

def test_speed_baselines_accumulate():
    base = {}
    for t in (200, 220, 180, 210):
        base = update_speed_baselines(base, "Medium", t, t + 100)
    entry = base["Medium"]
    assert entry["n"] == 4
    assert 180 <= entry["understand_mean"] <= 220
    assert entry["understand_std"] > 0

def test_personal_baseline_shifts_recall():
    """A user who is habitually slow shouldn't be punished for their normal pace."""
    slow_user = {}
    for _ in range(5):
        slow_user = update_speed_baselines(slow_user, "Medium", 600, 900)
    # 600s understand is average FOR THEM, so recall shouldn't be near-zero like the global default would give.
    personal, _ = derive_signals(slow_user, "Medium", 600, 900, num_submissions=1, hints_used=0)
    global_default, _ = derive_signals({}, "Medium", 600, 900, num_submissions=1, hints_used=0)
    assert personal > global_default


# --- retention curve ---

def test_retrievability_immediate_is_one():
    now = datetime.utcnow()
    assert predict_retrievability(2.0, now, DEFAULT_DECAY_EXPONENT, current_time=now) == 1.0

def test_retrievability_monotonic_decay():
    now = datetime.utcnow()
    r1 = predict_retrievability(2.0, now - timedelta(days=1), current_time=now)
    r5 = predict_retrievability(2.0, now - timedelta(days=5), current_time=now)
    r20 = predict_retrievability(2.0, now - timedelta(days=20), current_time=now)
    assert r1 > r5 > r20

def test_higher_decay_exponent_forgets_faster():
    now = datetime.utcnow()
    slow = predict_retrievability(2.0, now - timedelta(days=10), decay_exponent=0.3, current_time=now)
    fast = predict_retrievability(2.0, now - timedelta(days=10), decay_exponent=0.9, current_time=now)
    assert fast < slow

def test_default_matches_textbook_fsrs():
    """With w=0.5 our curve equals the original fsrs.calculate_retrievability."""
    from backend.fsrs import calculate_retrievability
    now = datetime.utcnow()
    lr = now - timedelta(days=7)
    assert abs(predict_retrievability(3.0, lr, 0.5, now) - calculate_retrievability(3.0, lr, now)) < 1e-6


# --- stability / difficulty updates ---

def test_strong_recall_grows_stability():
    assert update_stability(4.0, recall_strength=0.9, perceived_difficulty=5.0) > 4.0

def test_weak_recall_shrinks_stability():
    assert update_stability(4.0, recall_strength=0.1, perceived_difficulty=8.0) < 4.0

def test_midpoint_recall_is_neutral():
    assert abs(update_stability(4.0, recall_strength=0.5, perceived_difficulty=5.0) - 4.0) < 1e-6

def test_low_confidence_softens_update():
    full = update_stability(4.0, 0.9, 5.0, confidence_weight=1.0)
    low = update_stability(4.0, 0.9, 5.0, confidence_weight=0.3)
    assert 4.0 < low < full

def test_difficulty_pulls_toward_perceived():
    up = update_difficulty(5.0, perceived_difficulty=9.0)
    down = update_difficulty(5.0, perceived_difficulty=2.0)
    assert 5.0 < up <= 10.0
    assert 1.0 <= down < 5.0


# --- parameter fitting ---

def test_fit_decay_needs_minimum_samples():
    # Below the threshold, the current value is returned unchanged.
    assert fit_decay_exponent([(5.0, 2.0, 0.5)], current=0.5) == 0.5

def test_fit_decay_recovers_true_exponent():
    """Synthesize revisits from a known 'true' exponent; the fit should move toward it."""
    true_w = 0.9
    samples = []
    for elapsed, stability in [(2, 2), (5, 2), (8, 3), (12, 3), (3, 1.5),
                               (7, 2.5), (15, 4), (20, 5), (10, 2), (6, 3)]:
        observed = (1.0 + elapsed / (9.0 * stability)) ** (-true_w)
        samples.append((float(elapsed), float(stability), observed))
    fitted = fit_decay_exponent(samples, current=0.5)
    # Starting from 0.5, the fit should move meaningfully toward 0.9.
    assert fitted > 0.5

def test_fit_decay_reduces_error():
    true_w = 0.8
    samples = []
    for elapsed, stability in [(2, 2), (5, 2), (8, 3), (12, 3), (3, 1.5),
                               (7, 2.5), (15, 4), (20, 5), (10, 2), (6, 3)]:
        observed = (1.0 + elapsed / (9.0 * stability)) ** (-true_w)
        samples.append((float(elapsed), float(stability), observed))

    def mse(w):
        return sum(((1.0 + e / (9.0 * s)) ** (-w) - o) ** 2 for e, s, o in samples) / len(samples)

    fitted = fit_decay_exponent(samples, current=0.5)
    assert mse(fitted) < mse(0.5)


# --- prioritization ---

def test_revision_priority_scales_with_risk_and_urgency():
    assert revision_priority(0.8, 1.0, 1.0) > revision_priority(0.3, 1.0, 1.0)
    assert revision_priority(0.5, 1.0, 2.0) > revision_priority(0.5, 1.0, 1.0)

def test_prerequisite_boost_raises_importance_for_weak_dependents():
    assert prerequisite_boost(1.0, weak_dependents=0) == 1.0
    assert prerequisite_boost(1.0, weak_dependents=3) > 1.0
