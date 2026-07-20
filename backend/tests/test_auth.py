"""Auth unit tests: JWT lifecycle, the get_current_user guard, and Google upsert/onboarding."""
import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select
from sqlmodel.pool import StaticPool

from backend.models import User, Topic, KnowledgeNode, UserMemoryParams
from backend.auth import (
    create_access_token, decode_token, get_current_user,
    upsert_user_from_google,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for name in ["Arrays", "Graphs", "Dynamic Programming"]:
            s.add(Topic(name=name, description=""))
        s.commit()
        yield s


def test_jwt_roundtrip():
    payload = decode_token(create_access_token("user-123"))
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_get_current_user_valid(db):
    user = User(name="A", email="a@x.io")
    db.add(user); db.commit(); db.refresh(user)
    got = get_current_user(authorization=f"Bearer {create_access_token(user.id)}", session=db)
    assert got.id == user.id


def test_get_current_user_missing_header(db):
    with pytest.raises(HTTPException) as e:
        get_current_user(authorization=None, session=db)
    assert e.value.status_code == 401


def test_get_current_user_not_bearer(db):
    with pytest.raises(HTTPException) as e:
        get_current_user(authorization="Token abc", session=db)
    assert e.value.status_code == 401


def test_get_current_user_garbage_token(db):
    with pytest.raises(HTTPException) as e:
        get_current_user(authorization="Bearer not-a-jwt", session=db)
    assert e.value.status_code == 401


def test_get_current_user_expired_token(db):
    user = User(name="A", email="a@x.io")
    db.add(user); db.commit(); db.refresh(user)
    expired = create_access_token(user.id, expires_hours=-1)
    with pytest.raises(HTTPException) as e:
        get_current_user(authorization=f"Bearer {expired}", session=db)
    assert e.value.status_code == 401


def test_get_current_user_unknown_user(db):
    with pytest.raises(HTTPException) as e:
        get_current_user(authorization=f"Bearer {create_access_token('ghost-id')}", session=db)
    assert e.value.status_code == 401


def test_google_upsert_creates_and_onboards(db):
    user = upsert_user_from_google(db, {"email": "new@gmail.com", "name": "New User"})
    assert user.email == "new@gmail.com"
    assert db.get(UserMemoryParams, user.id) is not None
    nodes = db.exec(select(KnowledgeNode).where(KnowledgeNode.user_id == user.id)).all()
    assert len(nodes) == 3  # one per seeded topic


def test_google_upsert_is_idempotent(db):
    info = {"email": "dup@gmail.com", "name": "Dup"}
    u1 = upsert_user_from_google(db, info)
    u2 = upsert_user_from_google(db, info)
    assert u1.id == u2.id
    assert len(db.exec(select(User).where(User.email == "dup@gmail.com")).all()) == 1


def test_google_upsert_requires_email(db):
    with pytest.raises(HTTPException) as e:
        upsert_user_from_google(db, {"name": "No Email"})
    assert e.value.status_code == 400
