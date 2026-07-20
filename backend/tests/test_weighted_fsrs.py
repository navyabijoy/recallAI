"""
Tests for weighted FSRS calculations.
Verifies that the confidence_weight parameter correctly scales stability updates.
"""
import pytest
from backend.fsrs import update_fsrs_parameters, calculate_retrievability
from datetime import datetime, timedelta


def test_full_weight_good_rating():
    """With weight=1.0 and GOOD rating, stability should grow at full speed."""
    s, d = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="GOOD", confidence_weight=1.0)
    assert s > 4.0, "Stability should grow on GOOD"
    assert s <= 4.0 * 1.2, "Growth should be bounded"

def test_low_weight_good_rating():
    """With weight=0.3 (GitHub signal), stability grows more conservatively."""
    s_full, _ = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="GOOD", confidence_weight=1.0)
    s_low, _ = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="GOOD", confidence_weight=0.3)
    assert s_low < s_full, "Low weight should produce smaller stability growth"
    assert s_low > 4.0, "Low weight GOOD still grows stability"

def test_full_weight_again_decay():
    """With weight=1.0 and AGAIN rating, stability should decay significantly."""
    s, d = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="AGAIN", confidence_weight=1.0)
    assert s < 4.0, "AGAIN should decay stability"
    assert s < 4.0 * 0.6, "Full decay should be strong"

def test_low_weight_again_softer_decay():
    """With weight=0.3 and AGAIN rating, decay should be softer."""
    s_full, _ = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="AGAIN", confidence_weight=1.0)
    s_low, _ = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="AGAIN", confidence_weight=0.3)
    assert s_low > s_full, "Lower weight should cause softer decay on AGAIN"

def test_zero_weight_no_change():
    """With weight=0.0, stability should barely change."""
    s, _ = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="GOOD", confidence_weight=0.0)
    # With weight=0.0, growth_factor = 0.0, so new_stability = stability * (1 + 0) = stability
    assert abs(s - 4.0) < 0.01, "Zero weight should mean no stability change"

def test_difficulty_delta_scales_with_weight():
    """Difficulty adjustment should scale with weight."""
    _, d_full = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="AGAIN", confidence_weight=1.0)
    _, d_low = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="AGAIN", confidence_weight=0.3)
    # AGAIN increases difficulty. Full weight → bigger increase.
    assert d_full > d_low, "Full weight should cause larger difficulty increase on AGAIN"

def test_easy_weight_interaction():
    """EASY rating should reduce difficulty, scaled by weight."""
    _, d_full = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="EASY", confidence_weight=1.0)
    _, d_low = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="EASY", confidence_weight=0.3)
    assert d_full < 5.0, "EASY should reduce difficulty"
    assert d_full < d_low, "Full weight EASY should reduce difficulty more"

def test_stability_clamp_min():
    """Stability should never fall below 0.1."""
    s, _ = update_fsrs_parameters(stability=0.15, difficulty=10.0, rating="AGAIN", confidence_weight=1.0)
    assert s >= 0.1

def test_stability_clamp_max():
    """Stability should never exceed 3650 days (10 years)."""
    s, _ = update_fsrs_parameters(stability=3645.0, difficulty=1.0, rating="EASY", confidence_weight=1.0)
    assert s <= 3650.0

def test_retrievability_with_stability():
    """Higher stability should mean higher retrievability after the same time elapsed."""
    base_time = datetime.utcnow() - timedelta(days=3)
    r_high = calculate_retrievability(stability=10.0, last_review=base_time)
    r_low = calculate_retrievability(stability=2.0, last_review=base_time)
    assert r_high > r_low, "Higher stability → higher retrievability after same elapsed time"

def test_github_weight_constant():
    """GitHub should always use weight 0.3 per system design spec."""
    from backend.sync.scheduler import get_platform_weight
    assert get_platform_weight("github") == 0.3

def test_leetcode_weight_constant():
    """LeetCode should always use weight 1.0."""
    from backend.sync.scheduler import get_platform_weight
    assert get_platform_weight("leetcode") == 1.0

def test_codeforces_weight_constant():
    """Codeforces should always use weight 1.0."""
    from backend.sync.scheduler import get_platform_weight
    assert get_platform_weight("codeforces") == 1.0
