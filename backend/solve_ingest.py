"""
Solve ingestion pipeline.

One place that turns an incoming solve (from the browser extension, an API
backfill, or a manual log) into: a canonical Problem, a rich SolveAttempt, and
updated per-topic memory state + per-user model parameters.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select, and_

from .models import (
    User, Topic, KnowledgeNode, Problem, ProblemTopicLink,
    SolveAttempt, UserMemoryParams,
)
from .telemetry import derive_signals, update_speed_baselines, normalize_difficulty
from .memory_model import (
    predict_retrievability, update_stability, update_difficulty, fit_decay_exponent,
    DEFAULT_DECAY_EXPONENT, DEFAULT_STABILITY_GROWTH, MIN_ATTEMPTS_TO_FIT,
)
from .sync.leetcode import TAG_MAPPING as LEETCODE_TAG_MAPPING

logger = logging.getLogger(__name__)

# Codeforces problem tags → RecallAI graph topics.
CODEFORCES_TAG_MAPPING = {
    "dp": "Dynamic Programming",
    "dynamic programming": "Dynamic Programming",
    "graphs": "Graphs",
    "dfs and similar": "Graphs",
    "shortest paths": "Graphs",
    "graph matchings": "Graphs",
    "dsu": "Union Find",
    "binary search": "Binary Search",
    "ternary search": "Binary Search",
    "two pointers": "Arrays",
    "implementation": "Arrays",
    "brute force": "Arrays",
    "data structures": "Heap",
    "trees": "Trees",
    "strings": "Strings",
    "string suffix structures": "Trie",
    "hashing": "Hash Table",
    "greedy": "Greedy",
    "constructive algorithms": "Greedy",
    "math": "Math",
    "number theory": "Math",
    "combinatorics": "Math",
    "sortings": "Sorting",
    "bitmasks": "Bit Manipulation",
    "divide and conquer": "Binary Search",
}

# How much each ingest source is trusted (scales the strength of memory updates).
SOURCE_WEIGHTS = {"extension": 1.0, "manual": 0.8, "api_backfill": 0.4}


def map_tags_to_topics(platform: str, raw_tags: List[str]) -> List[str]:
    """Maps raw platform tag slugs/labels to distinct RecallAI topic names."""
    mapping = LEETCODE_TAG_MAPPING if platform == "leetcode" else CODEFORCES_TAG_MAPPING
    topics: List[str] = []
    for tag in raw_tags or []:
        key = str(tag).strip().lower()
        topic = mapping.get(key)
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def _get_or_create_params(session: Session, user_id: str) -> UserMemoryParams:
    params = session.get(UserMemoryParams, user_id)
    if not params:
        params = UserMemoryParams(
            user_id=user_id,
            decay_exponent=DEFAULT_DECAY_EXPONENT,
            stability_growth=DEFAULT_STABILITY_GROWTH,
            speed_baselines={},
        )
        session.add(params)
    return params


def _link_topics(session: Session, problem: Problem, platform: str, raw_tags: List[str]) -> None:
    """Creates ProblemTopicLinks for any mapped topics not already linked."""
    # Query link rows directly rather than problem.topics — accessing the
    # relationship here would cache a stale (empty) collection that the caller
    # then reads back before it reflects the rows we add below.
    linked = {
        l.topic_id for l in session.exec(
            select(ProblemTopicLink).where(ProblemTopicLink.problem_id == problem.id)
        ).all()
    }
    changed = False
    for topic_name in map_tags_to_topics(platform, raw_tags):
        topic = session.exec(select(Topic).where(Topic.name == topic_name)).first()
        if topic and topic.id not in linked:
            session.add(ProblemTopicLink(problem_id=problem.id, topic_id=topic.id))
            linked.add(topic.id)
            changed = True
    session.flush()
    if changed:
        session.expire(problem, ["topics"])  # force a fresh load on next access


def _upsert_problem(session: Session, payload: Dict[str, Any]) -> Problem:
    platform = str(payload.get("platform", "")).lower()
    ppid = str(payload.get("platform_problem_id", "")).strip()
    payload_tags = payload.get("topic_tags") or []
    problem = session.exec(
        select(Problem).where(
            and_(Problem.platform == platform, Problem.platform_problem_id == ppid)
        )
    ).first()

    if problem:
        # Self-heal: a problem created before our tag mappings existed (or before
        # tags were scraped) has no topic links. Backfill them from stored or
        # incoming tags so past solves start counting toward topics.
        if not problem.topics:
            tags = problem.topic_tags or payload_tags
            if payload_tags and not problem.topic_tags:
                problem.topic_tags = payload_tags  # remember tags we just learned
            _link_topics(session, problem, platform, tags)
        return problem

    problem = Problem(
        platform=platform,
        platform_problem_id=ppid,
        title=payload.get("title"),
        url=payload.get("url"),
        difficulty=payload.get("difficulty"),
        topic_tags=payload_tags,
    )
    session.add(problem)
    session.flush()  # assign problem.id
    _link_topics(session, problem, platform, payload_tags)
    return problem


def _refit_user_decay(session: Session, params: UserMemoryParams) -> None:
    """Refit the personal forgetting exponent from this user's revisit history."""
    if params.attempts_observed < MIN_ATTEMPTS_TO_FIT:
        return
    attempts = session.exec(
        select(SolveAttempt).where(SolveAttempt.user_id == params.user_id)
    ).all()
    samples = [
        (a.days_since_prev_review, a.stability_at_review, a.recall_strength)
        for a in attempts
        if a.days_since_prev_review and a.days_since_prev_review > 0
        and a.stability_at_review and a.recall_strength is not None
    ]
    if len(samples) >= MIN_ATTEMPTS_TO_FIT:
        params.decay_exponent = fit_decay_exponent(samples, current=params.decay_exponent)


def ingest_solve(session: Session, user: User, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processes one solve. Returns a summary of the derived signals and which
    topics moved. Commits the session.
    """
    now = datetime.utcnow()
    source = str(payload.get("source", "extension")).lower()
    weight = SOURCE_WEIGHTS.get(source, 1.0)

    problem = _upsert_problem(session, payload)
    params = _get_or_create_params(session, user.id)

    difficulty = payload.get("difficulty") or problem.difficulty
    tu = payload.get("time_to_understand_s")
    tw = payload.get("time_to_write_s")
    num_submissions = int(payload.get("num_submissions", 1))
    hints_used = int(payload.get("hints_used", 0))
    verdict = str(payload.get("verdict", "Accepted"))

    recall_strength, perceived = derive_signals(
        params.speed_baselines, difficulty, tu, tw, num_submissions, hints_used, verdict
    )

    attempt = SolveAttempt(
        user_id=user.id,
        problem_id=problem.id,
        opened_at=_parse_dt(payload.get("opened_at")),
        first_keystroke_at=_parse_dt(payload.get("first_keystroke_at")),
        submitted_at=_parse_dt(payload.get("submitted_at")) or now,
        time_to_understand_s=tu,
        time_to_write_s=tw,
        num_submissions=num_submissions,
        hints_used=hints_used,
        verdict=verdict,
        source=source,
        confidence_weight=weight,
        recall_strength=recall_strength,
        perceived_difficulty=perceived,
    )
    session.add(attempt)

    # Update the user's speed baselines from this solve.
    params.speed_baselines = update_speed_baselines(params.speed_baselines, difficulty, tu, tw)
    params.attempts_observed += 1
    params.updated_at = now

    # Update memory state for every topic this problem exercises.
    updated_topics: List[Dict[str, Any]] = []
    for topic in problem.topics:
        node = session.exec(
            select(KnowledgeNode).where(
                and_(KnowledgeNode.user_id == user.id, KnowledgeNode.topic_id == topic.id)
            )
        ).first()
        if not node:
            node = KnowledgeNode(
                user_id=user.id, topic_id=topic.id,
                fsrs_stability=2.0, fsrs_difficulty=5.0, last_review=now, practice_count=0,
            )
            session.add(node)

        # Capture review-time state on the attempt (once) for later parameter fitting.
        if attempt.stability_at_review is None:
            elapsed_days = max(0.0, (now - node.last_review).total_seconds() / 86400.0)
            attempt.days_since_prev_review = elapsed_days
            attempt.stability_at_review = node.fsrs_stability

        node.fsrs_stability = update_stability(
            node.fsrs_stability, recall_strength, perceived, params.stability_growth, weight
        )
        node.fsrs_difficulty = update_difficulty(node.fsrs_difficulty, perceived, weight)
        node.last_review = now
        node.practice_count += 1
        updated_topics.append({"topic": topic.name, "new_stability": node.fsrs_stability})

    _refit_user_decay(session, params)
    session.commit()
    session.refresh(attempt)

    return {
        "status": "success",
        "attempt_id": attempt.id,
        "problem": problem.title or problem.platform_problem_id,
        "recall_strength": recall_strength,
        "perceived_difficulty": perceived,
        "updated_topics": updated_topics,
        "unmapped": len(updated_topics) == 0,
        "decay_exponent": params.decay_exponent,
    }


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None
