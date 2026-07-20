"""
Multi-user isolation: two users authenticate with their own Bearer tokens and
can only ever see their own data through the /api/me/* endpoints.
"""
import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import get_session, User, Topic
from backend.auth import create_access_token, onboard_user
from backend.solve_ingest import ingest_solve


@pytest.fixture
def ctx():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    for name in ["Arrays", "Graphs"]:
        session.add(Topic(name=name, description=""))
    session.commit()

    a = User(name="A", email="a@x.io")
    b = User(name="B", email="b@x.io")
    session.add(a); session.add(b); session.commit()
    session.refresh(a); session.refresh(b)
    onboard_user(session, a)
    onboard_user(session, b)

    # Only user A solves something.
    ingest_solve(session, a, {
        "platform": "leetcode", "platform_problem_id": "two-sum", "title": "Two Sum",
        "difficulty": "Easy", "topic_tags": ["array"],
        "time_to_understand_s": 60, "time_to_write_s": 120,
        "verdict": "Accepted", "source": "extension",
    })

    # Route every request's DB session to this in-memory one (no lifespan/startup).
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)
    yield client, a, b
    app.dependency_overrides.clear()
    session.close()


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_solve_attempts_are_isolated(ctx):
    client, a, b = ctx
    ra = client.get("/api/me/solve-attempts", headers=_auth(a))
    rb = client.get("/api/me/solve-attempts", headers=_auth(b))
    assert ra.status_code == 200 and rb.status_code == 200
    assert len(ra.json()) == 1       # A sees their solve
    assert len(rb.json()) == 0       # B sees none of A's data


def test_revision_queue_is_isolated(ctx):
    client, a, b = ctx
    qa = client.get("/api/me/revision-queue", headers=_auth(a)).json()
    qb = client.get("/api/me/revision-queue", headers=_auth(b)).json()
    a_arrays = next(x for x in qa["queue"] if x["topic"] == "Arrays")
    b_arrays = next(x for x in qb["queue"] if x["topic"] == "Arrays")
    assert a_arrays["practice_count"] >= 1
    assert b_arrays["practice_count"] == 0


def test_me_endpoint_returns_the_right_user(ctx):
    client, a, b = ctx
    assert client.get("/api/auth/me", headers=_auth(a)).json()["email"] == "a@x.io"
    assert client.get("/api/auth/me", headers=_auth(b)).json()["email"] == "b@x.io"


def test_endpoints_require_auth(ctx):
    client, _, _ = ctx
    assert client.get("/api/me/revision-queue").status_code == 401
    assert client.get("/api/me/solve-attempts").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
