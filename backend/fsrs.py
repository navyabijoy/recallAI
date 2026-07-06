from datetime import datetime, timezone

def calculate_retrievability(stability: float, last_review: datetime, current_time: datetime = None) -> float:
    """
    Calculates Retrievability (R) of a concept using the FSRS retrievability formula:
    R = (1 + t / (9 * S)) ** -0.5
    Where:
      - t is the time elapsed in days since the last review.
      - S is the stability (retention rate).
    """
    if current_time is None:
        current_time = datetime.utcnow()
        
    # Standardize timezones if present, or work with naive utc datetimes
    if last_review.tzinfo is not None:
        last_review = last_review.astimezone(timezone.utc).replace(tzinfo=None)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)
        
    delta = current_time - last_review
    t = max(0.0, delta.total_seconds() / (24 * 3600))  # Convert elapsed seconds to days
    
    # Avoid division by zero
    if stability <= 0:
        stability = 0.1
        
    retrievability = (1.0 + t / (9.0 * stability)) ** -0.5
    return min(1.0, max(0.0, retrievability))

def update_fsrs_parameters(stability: float, difficulty: float, rating: str) -> tuple[float, float]:
    """
    Updates the stability (S) and difficulty (D) parameters for a topic based on a review rating.
    Ratings are: "AGAIN", "HARD", "GOOD", "EASY"
    
    Returns:
      (new_stability, new_difficulty)
    """
    # 1. Update Difficulty (D)
    # AGAIN adds difficulty, EASY reduces, GOOD keeps it stable
    difficulty_deltas = {
        "AGAIN": 1.5,
        "HARD": 0.5,
        "GOOD": 0.0,
        "EASY": -1.0
    }
    
    delta_d = difficulty_deltas.get(rating.upper(), 0.0)
    new_difficulty = max(1.0, min(10.0, difficulty + delta_d))
    
    # 2. Update Stability (S)
    if rating.upper() == "AGAIN":
        # Concept was forgotten. Reduce stability.
        new_stability = stability * 0.5
    else:
        # Concept was recalled successfully. Grow stability.
        # Factor is scaled by how difficult the concept is (higher difficulty -> slower growth)
        difficulty_factor = max(1.0, difficulty) ** -0.2
        
        # Scaling multiplier based on review quality
        rating_multipliers = {
            "HARD": 0.05,
            "GOOD": 0.1,
            "EASY": 0.2
        }
        multiplier = rating_multipliers.get(rating.upper(), 0.1)
        new_stability = stability * (1.0 + multiplier * difficulty_factor)
        
    # Ensure stability doesn't fall below a safe minimum or grow excessively
    new_stability = max(0.1, min(3650.0, new_stability)) # Max 10 years stability
    
    return round(new_stability, 4), round(new_difficulty, 4)
