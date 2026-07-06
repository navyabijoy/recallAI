from datetime import datetime, timedelta
from backend.fsrs import calculate_retrievability, update_fsrs_parameters

def test_calculate_retrievability_immediate():
    # Immediate recall should have retrievability = 1.0
    last_review = datetime.utcnow()
    assert calculate_retrievability(stability=2.0, last_review=last_review, current_time=last_review) == 1.0

def test_calculate_retrievability_decay():
    # Retrievability decays as time passes
    last_review = datetime.utcnow() - timedelta(days=9)
    # With stability=1.0, elapsed t=9 days, R = (1 + 9/(9*1))**-0.5 = 2**-0.5 approx 0.707
    r = calculate_retrievability(stability=1.0, last_review=last_review)
    assert 0.70 < r < 0.71

def test_update_fsrs_again():
    # AGAIN rating halves stability and increases difficulty
    s, d = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="AGAIN")
    assert s == 2.0
    assert d == 6.5

def test_update_fsrs_good():
    # GOOD rating grows stability and keeps difficulty unchanged
    s, d = update_fsrs_parameters(stability=4.0, difficulty=5.0, rating="GOOD")
    assert s > 4.0
    assert d == 5.0

def test_update_fsrs_clamping():
    # Difficulty is clamped to maximum 10.0 and minimum 1.0
    _, d_max = update_fsrs_parameters(stability=2.0, difficulty=9.5, rating="AGAIN")
    assert d_max == 10.0
    
    _, d_min = update_fsrs_parameters(stability=2.0, difficulty=1.5, rating="EASY")
    assert d_min == 1.0
