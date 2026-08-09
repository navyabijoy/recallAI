import os
import uuid
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlmodel import Field, SQLModel, Relationship, JSON, Column, create_engine, Session
from sqlalchemy import UniqueConstraint

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./recallai.db")

# Adjust SQLite settings for concurrency if using SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

def get_session():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Many-to-many relationship helper table for Topic prerequisites
class TopicPrerequisiteLink(SQLModel, table=True):
    topic_id: str = Field(foreign_key="topic.id", primary_key=True)
    prerequisite_id: str = Field(foreign_key="topic.id", primary_key=True)

class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    preferences: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    # Relationships
    events: List["LearningEvent"] = Relationship(back_populates="user", cascade_delete=True)
    knowledge_nodes: List["KnowledgeNode"] = Relationship(back_populates="user", cascade_delete=True)
    agent_logs: List["AgentLog"] = Relationship(back_populates="user", cascade_delete=True)
    sync_sources: List["SyncSource"] = Relationship(back_populates="user", cascade_delete=True)
    calendar_connections: List["CalendarConnection"] = Relationship(back_populates="user", cascade_delete=True)
    solve_attempts: List["SolveAttempt"] = Relationship(back_populates="user", cascade_delete=True)
    memory_params: Optional["UserMemoryParams"] = Relationship(back_populates="user", cascade_delete=True)
    api_keys: List["ApiKey"] = Relationship(back_populates="user", cascade_delete=True)

class Topic(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(unique=True, index=True)
    description: Optional[str] = None

    # Relationships
    events: List["LearningEvent"] = Relationship(back_populates="topic", cascade_delete=True)
    knowledge_nodes: List["KnowledgeNode"] = Relationship(back_populates="topic", cascade_delete=True)

class LearningEvent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    topic_id: str = Field(foreign_key="topic.id", index=True)
    difficulty: str  # "AGAIN", "HARD", "GOOD", "EASY"
    duration_min: int
    mistakes: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="events")
    topic: Topic = Relationship(back_populates="events")

class KnowledgeNode(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    topic_id: str = Field(foreign_key="topic.id", index=True)
    fsrs_stability: float = Field(default=2.0)  # S parameter in days
    fsrs_difficulty: float = Field(default=5.0)  # D parameter [1.0, 10.0]
    last_review: datetime = Field(default_factory=datetime.utcnow)
    practice_count: int = Field(default=0)

    # Relationships
    user: User = Relationship(back_populates="knowledge_nodes")
    topic: Topic = Relationship(back_populates="knowledge_nodes")

class AgentLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_calls: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    final_plan: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    reasoning: str
    calendar_context: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    deadline_context: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    # Relationships
    user: User = Relationship(back_populates="agent_logs")


class SyncSource(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    platform: str  # "leetcode", "github", "codeforces"
    status: str = Field(default="active")  # "active", "error", "disconnected"
    last_synced_at: Optional[datetime] = None
    auth_token: Optional[str] = None  # Or cookie / config JSON

    # Relationships
    user: User = Relationship(back_populates="sync_sources")
    raw_events: List["RawSyncEvent"] = Relationship(back_populates="sync_source", cascade_delete=True)


class RawSyncEvent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    sync_source_id: str = Field(foreign_key="syncsource.id", index=True)
    raw_payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    mapped_topic_id: Optional[str] = Field(default=None, foreign_key="topic.id", nullable=True)
    confidence_weight: float = Field(default=1.0)
    processed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    sync_source: SyncSource = Relationship(back_populates="raw_events")
    topic: Optional[Topic] = Relationship()


class CalendarConnection(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    provider: str = Field(default="google")
    auth_token: Optional[str] = None  # JSON credentials or refresh token
    last_synced_at: Optional[datetime] = None

    # Relationships
    user: User = Relationship(back_populates="calendar_connections")


# --- M1: Telemetry-driven personalized memory model ---

class ProblemTopicLink(SQLModel, table=True):
    """Many-to-many: a canonical Problem tests one or more of our graph Topics."""
    problem_id: str = Field(foreign_key="problem.id", primary_key=True)
    topic_id: str = Field(foreign_key="topic.id", primary_key=True)


class Problem(SQLModel, table=True):
    """
    Canonical identity of a real coding problem (shared across all users).
    A single problem may map to several RecallAI topics via ProblemTopicLink.
    """
    __table_args__ = (
        UniqueConstraint("platform", "platform_problem_id", name="uq_problem_platform_ppid"),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    platform: str = Field(index=True)              # "leetcode", "codeforces"
    platform_problem_id: str = Field(index=True)   # slug ("two-sum") or CF "1520/D"
    title: Optional[str] = None
    url: Optional[str] = None
    difficulty: Optional[str] = None               # "Easy"/"Medium"/"Hard" or CF rating as str
    topic_tags: List[str] = Field(default_factory=list, sa_column=Column(JSON))  # raw platform tags
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    topics: List["Topic"] = Relationship(link_model=ProblemTopicLink)
    attempts: List["SolveAttempt"] = Relationship(back_populates="problem", cascade_delete=True)


class SolveAttempt(SQLModel, table=True):
    """
    Rich per-solve telemetry record. This is the real signal that drives the
    personalized memory model (replaces manual GOOD/HARD self-grades).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    problem_id: str = Field(foreign_key="problem.id", index=True)

    # Client-generated idempotency key (one per problem-solve session). Lets the
    # extension safely retry a POST (reload, offline queue, multi-tab) without
    # creating duplicate rows that would corrupt the memory model. NULLs (manual/
    # api_backfill entries with no client) are exempt from the uniqueness check.
    client_event_id: Optional[str] = Field(default=None, unique=True, index=True)

    # Timing telemetry (seconds). understand = first_keystroke - opened; write = submitted - first_keystroke.
    opened_at: Optional[datetime] = None
    first_keystroke_at: Optional[datetime] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    time_to_understand_s: Optional[int] = None
    time_to_write_s: Optional[int] = None

    # Struggle signals
    num_submissions: int = Field(default=1)
    hints_used: int = Field(default=0)
    verdict: str = Field(default="Accepted")       # "Accepted", "Wrong Answer", "TLE", ...

    # Provenance + derived model outputs
    source: str = Field(default="extension")       # "extension" | "api_backfill" | "manual"
    confidence_weight: float = Field(default=1.0)
    recall_strength: Optional[float] = None         # derived [0,1]
    perceived_difficulty: Optional[float] = None    # derived [1,10], relative to this user

    # State captured at review time so the decay exponent can be fit later
    # (how well our prediction matched what the user actually recalled).
    days_since_prev_review: Optional[float] = None
    stability_at_review: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="solve_attempts")
    problem: Problem = Relationship(back_populates="attempts")


class UserMemoryParams(SQLModel, table=True):
    """
    Per-user fitted coefficients of the memory model. Seeded with global
    FSRS-equivalent priors and updated as telemetry accumulates.
    Speed baselines are per-difficulty running means/std (JSON keyed by difficulty).
    """
    user_id: str = Field(foreign_key="user.id", primary_key=True)
    decay_exponent: float = Field(default=0.5)      # w: forgetting-curve exponent (FSRS prior = 0.5)
    stability_growth: float = Field(default=0.15)   # g: stability growth per unit recall_strength
    # {"Easy": {"understand_mean": 120, "understand_std": 60, "write_mean": 300, "write_std": 120, "n": 4}, ...}
    speed_baselines: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    attempts_observed: int = Field(default=0)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="memory_params")


class ApiKey(SQLModel, table=True):
    """Credential the browser extension uses to authenticate telemetry posts."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    key: str = Field(default_factory=lambda: "rk_" + secrets.token_urlsafe(24), unique=True, index=True)
    label: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
    revoked: bool = Field(default=False)

    # Relationships
    user: User = Relationship(back_populates="api_keys")
