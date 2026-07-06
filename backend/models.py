import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlmodel import Field, SQLModel, Relationship, JSON, Column, create_engine, Session

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

    # Relationships
    user: User = Relationship(back_populates="agent_logs")
