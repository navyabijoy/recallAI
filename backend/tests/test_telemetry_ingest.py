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
