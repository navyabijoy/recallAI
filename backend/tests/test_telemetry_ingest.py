"""
End-to-end tests for the solve-telemetry ingestion pipeline against an
isolated in-memory database (does not touch recallai.db).
"""
import pytest
from datetime import datetime, timedelta
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

from backend.models import (
    User, Topic, TopicPrerequisiteLink, KnowledgeNode,
    Problem, SolveAttempt, UserMemoryParams,
)
from backend.solve_ingest import ingest_solve, map_tags_to_topics


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(id="u1", name="Test", email="t@test.io")
        s.add(user)
        arrays = Topic(name="Arrays", description="")
        graphs = Topic(name="Graphs", description="")
        dp = Topic(name="Dynamic Programming", description="")
        s.add(arrays); s.add(graphs); s.add(dp)
        s.commit()
        # Graphs -> Dynamic Programming prerequisite link (prereq_id=Graphs).
        s.refresh(graphs); s.refresh(dp)
        s.add(TopicPrerequisiteLink(topic_id=dp.id, prerequisite_id=graphs.id))
        s.commit()
        yield s


def _payload(**overrides):
    base = {
        "platform": "leetcode",
        "platform_problem_id": "two-sum",
        "title": "Two Sum",
        "url": "https://leetcode.com/problems/two-sum/",
        "difficulty": "Easy",
        "topic_tags": ["array"],
        "time_to_understand_s": 60,
        "time_to_write_s": 120,
        "num_submissions": 1,
        "hints_used": 0,
        "verdict": "Accepted",
        "source": "extension",
    }
    base.update(overrides)
    return base


def test_tag_mapping():
    assert map_tags_to_topics("leetcode", ["array", "two-pointers"]) == ["Arrays"]
    assert map_tags_to_topics("codeforces", ["dp", "graphs"]) == ["Dynamic Programming", "Graphs"]
    assert map_tags_to_topics("leetcode", ["unknown-tag"]) == []


def test_ingest_creates_problem_attempt_and_node(session):
    user = session.get(User, "u1")
    result = ingest_solve(session, user, _payload())

    assert result["status"] == "success"
    assert result["unmapped"] is False
    assert any(t["topic"] == "Arrays" for t in result["updated_topics"])

    problem = session.exec(select(Problem).where(Problem.platform_problem_id == "two-sum")).first()
    assert problem is not None
    assert [t.name for t in problem.topics] == ["Arrays"]

    attempt = session.exec(select(SolveAttempt)).first()
    assert attempt is not None
    assert 0.0 <= attempt.recall_strength <= 1.0
    assert attempt.stability_at_review is not None  # captured for later fitting

    node = session.exec(select(KnowledgeNode).where(KnowledgeNode.user_id == "u1")).first()
    assert node is not None
    assert node.practice_count == 1


def test_problem_is_deduped_across_attempts(session):
    user = session.get(User, "u1")
    ingest_solve(session, user, _payload())
    ingest_solve(session, user, _payload(time_to_understand_s=90))
    problems = session.exec(select(Problem)).all()
    assert len(problems) == 1
    attempts = session.exec(select(SolveAttempt)).all()
    assert len(attempts) == 2


def test_strong_solve_raises_stability_more_than_weak(session):
    user = session.get(User, "u1")
    ingest_solve(session, user, _payload(platform_problem_id="p-strong",
                                         time_to_understand_s=30, time_to_write_s=60))
    strong_node = session.exec(
        select(KnowledgeNode).join(Topic).where(Topic.name == "Arrays")
    ).first()
    strong_stability = strong_node.fsrs_stability

    # Reset the node, then a weak solve on the same topic.
    strong_node.fsrs_stability = 2.0
    session.add(strong_node)
    session.commit()
    ingest_solve(session, user, _payload(platform_problem_id="p-weak",
                                         time_to_understand_s=900, time_to_write_s=1800,
                                         num_submissions=5, hints_used=3, verdict="Wrong Answer"))
    weak_node = session.exec(
        select(KnowledgeNode).join(Topic).where(Topic.name == "Arrays")
    ).first()
    assert weak_node.fsrs_stability < strong_stability


def test_unmapped_problem_still_records(session):
    user = session.get(User, "u1")
    result = ingest_solve(session, user, _payload(platform_problem_id="mystery", topic_tags=["greedy"]))
    assert result["unmapped"] is True
    assert session.exec(select(Problem).where(Problem.platform_problem_id == "mystery")).first() is not None


def test_memory_params_track_attempts(session):
    user = session.get(User, "u1")
    for i in range(3):
        ingest_solve(session, user, _payload(platform_problem_id=f"p{i}"))
    params = session.get(UserMemoryParams, "u1")
    assert params is not None
    assert params.attempts_observed == 3
    assert "Easy" in params.speed_baselines


# --- Phase 0: idempotency + uniqueness ---

def test_duplicate_client_event_id_is_a_no_op(session):
    """A retried POST (reload, offline queue, two tabs) must not double-count."""
    user = session.get(User, "u1")
    payload = _payload(client_event_id="evt-123")

    first = ingest_solve(session, user, payload)
    assert first["status"] == "success"

    second = ingest_solve(session, user, payload)
    assert second["status"] == "duplicate"
    assert second["attempt_id"] == first["attempt_id"]

    attempts = session.exec(select(SolveAttempt)).all()
    assert len(attempts) == 1

    params = session.get(UserMemoryParams, "u1")
    assert params.attempts_observed == 1  # not bumped a second time

    node = session.exec(select(KnowledgeNode).join(Topic).where(Topic.name == "Arrays")).first()
    assert node.practice_count == 1  # not bumped a second time


def test_duplicate_client_event_id_across_different_problems_still_dedups(session):
    """The idempotency key alone determines identity — a resend can't be
    reinterpreted as a different solve even if some other field changed."""
    user = session.get(User, "u1")
    ingest_solve(session, user, _payload(client_event_id="evt-456"))
    result = ingest_solve(session, user, _payload(client_event_id="evt-456", platform_problem_id="two-sum-ii"))
    assert result["status"] == "duplicate"
    assert len(session.exec(select(SolveAttempt)).all()) == 1


def test_missing_client_event_id_does_not_dedup(session):
    """Older/manual/api_backfill payloads with no client_event_id keep working
    as before — every post is treated as a distinct attempt."""
    user = session.get(User, "u1")
    ingest_solve(session, user, _payload())
    ingest_solve(session, user, _payload())
    assert len(session.exec(select(SolveAttempt)).all()) == 2


def test_problem_platform_and_id_are_unique(session):
    """Concurrent first-solves of the same problem must not create two Problem rows."""
    from sqlalchemy.exc import IntegrityError
    from backend.models import ProblemTopicLink

    p1 = Problem(platform="leetcode", platform_problem_id="two-sum")
    session.add(p1)
    session.commit()

    p2 = Problem(platform="leetcode", platform_problem_id="two-sum")
    session.add(p2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    assert len(session.exec(select(Problem).where(Problem.platform_problem_id == "two-sum")).all()) == 1
