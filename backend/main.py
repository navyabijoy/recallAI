import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, and_

from .models import (
    create_db_and_tables, get_session, User, Topic, LearningEvent,
    KnowledgeNode, AgentLog, TopicPrerequisiteLink, SyncSource, RawSyncEvent,
    CalendarConnection, Problem, SolveAttempt, UserMemoryParams, ApiKey, engine
)
from .fsrs import calculate_retrievability, update_fsrs_parameters
from .memory_model import predict_retrievability, revision_priority, prerequisite_boost, DEFAULT_DECAY_EXPONENT
from .graph_utils import get_related_concepts, get_all_reachable_dependents
from .solve_ingest import ingest_solve
from .agent import run_planning_agent, run_coach_agent
from .sync.scheduler import start_scheduler, shutdown_scheduler, sync_source_now
from .sync.base import SyncRegistry
from .sync.calendar_api import get_upcoming_deadlines

# Import adapters so they self-register in SyncRegistry
from .sync import leetcode, github, codeforces  # noqa: F401

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="RecallAI - Spaced Repetition Agent Backend", version="2.0.0")

# CORS middleware for Next.js frontend calls.
# NOTE: "*" origins with allow_credentials=True is an invalid combination that
# browsers reject. The web app authenticates by user_id in the path (no cookies),
# and the extension posts via its background worker (not subject to page CORS),
# so we don't need credentialed CORS — keep the wildcard and turn credentials off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup DB setup and auto-seeding
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    seed_dsa_data()
    ensure_topics_and_links()
    start_scheduler()

# Topics added after the original seed. `ensure_topics_and_links` is idempotent,
# so it upgrades an already-seeded database (adds missing topics, per-user
# knowledge nodes, and prerequisite links) without a wipe.
EXTRA_TOPICS = {
    "Linked List": "Pointer manipulation, fast/slow pointers, reversal, merge",
    "Math": "Number theory, combinatorics, modular arithmetic, GCD/LCM",
    "Recursion": "Base/recursive cases, call stack, divide and conquer",
    "Strings": "Pattern matching, parsing, two-pointer and sliding-window on text",
    "Greedy": "Locally optimal choices, exchange arguments, interval scheduling",
    "Stack": "LIFO structures, monotonic stack, expression evaluation",
    "Hash Table": "Hash maps/sets, counting, O(1) lookup, frequency patterns",
    "Backtracking": "Constraint search, permutations/combinations, pruning",
    "Sorting": "Comparison sorts, custom comparators, sort-then-scan",
    "Bit Manipulation": "Bitmasks, XOR tricks, bit counting, subsets",
    "Trees": "Binary trees, traversals, BST, recursion on trees",
}

# (topic, prerequisite) — prerequisite must be mastered first.
EXTRA_LINKS = [
    ("Backtracking", "Recursion"),
    ("Trees", "Recursion"),
    ("Dynamic Programming", "Recursion"),
    ("Trie", "Trees"),
    ("Graphs", "Trees"),
    ("Stack", "Linked List"),
]

def ensure_topics_and_links():
    """Adds any missing topics, per-user knowledge nodes, and prerequisite links."""
    with Session(engine) as session:
        existing = {t.name: t for t in session.exec(select(Topic)).all()}
        added = False
        for name, desc in EXTRA_TOPICS.items():
            if name not in existing:
                session.add(Topic(name=name, description=desc))
                added = True
        if added:
            session.commit()
            existing = {t.name: t for t in session.exec(select(Topic)).all()}

        # Ensure every user has a knowledge node for every topic.
        users = session.exec(select(User)).all()
        for user in users:
            have = {n.topic_id for n in session.exec(
                select(KnowledgeNode).where(KnowledgeNode.user_id == user.id)
            ).all()}
            for topic in existing.values():
                if topic.id not in have:
                    session.add(KnowledgeNode(
                        user_id=user.id, topic_id=topic.id,
                        fsrs_stability=1.0, fsrs_difficulty=6.0,
                        last_review=datetime.utcnow() - timedelta(days=7),
                        practice_count=0,
                    ))

        # Ensure prerequisite links (skip if either endpoint or the link is missing).
        have_links = {
            (l.topic_id, l.prerequisite_id)
            for l in session.exec(select(TopicPrerequisiteLink)).all()
        }
        for topic_name, prereq_name in EXTRA_LINKS:
            t, p = existing.get(topic_name), existing.get(prereq_name)
            if t and p and (t.id, p.id) not in have_links:
                session.add(TopicPrerequisiteLink(topic_id=t.id, prerequisite_id=p.id))

        session.commit()
        logger.info("Topic/link sync complete (%d topics).", len(existing))

@app.on_event("shutdown")
def on_shutdown():
    shutdown_scheduler()

def seed_dsa_data():
    """Seeds default user, topics, and dependency links if database is empty."""
    with Session(engine) as session:
        # Check if topics exist
        existing_topics = session.exec(select(Topic)).all()
        if existing_topics:
            logger.info("Database already seeded.")
            return

        logger.info("Seeding database with default DSA + Python + System Design topics...")
        # 1. Create default User
        default_user = User(
            id="demo-user-id",
            name="Navya",
            email="navya@recallai.io",
            preferences={"dailyStudyTimeMinutes": 120}
        )
        session.add(default_user)

        # 2. Create DSA Topics
        dsa_topics = {
            "Arrays": Topic(name="Arrays", description="Basic array manipulations, two pointers, prefix sums"),
            "Sliding Window": Topic(name="Sliding Window", description="Subarray constraints, variable and fixed size window algorithms"),
            "Binary Search": Topic(name="Binary Search", description="Divide and conquer, searching sorted spaces, search by answer"),
            "Heap": Topic(name="Heap", description="Priority queues, top K elements, heap sort"),
            "Trie": Topic(name="Trie", description="Prefix tree structures, word insert/search/prefix matches"),
            "Graphs": Topic(name="Graphs", description="Representations, BFS, DFS, shortest path algorithms"),
            "Union Find": Topic(name="Union Find", description="Disjoint set data structures, path compression, union by rank"),
            "Dynamic Programming": Topic(name="Dynamic Programming", description="Memoization, tabulation, state machines, knapsack problems"),
        }

        # 3. Create Python & System Design Topics
        sysdesign_topics = {
            "Python Functions": Topic(name="Python Functions", description="First-class functions, closures, decorators, higher-order functions"),
            "Python Concurrency": Topic(name="Python Concurrency", description="Threading, multiprocessing, asyncio, GIL, event loops"),
            "Load Balancers": Topic(name="Load Balancers", description="Round-robin, least connections, consistent hashing, L4 vs L7"),
            "Caching": Topic(name="Caching", description="LRU/LFU cache, Redis, cache invalidation strategies, cache aside pattern"),
            "Database Sharding": Topic(name="Database Sharding", description="Horizontal partitioning, shard keys, resharding, consistent hashing"),
        }

        all_topics = {**dsa_topics, **sysdesign_topics}
        for topic in all_topics.values():
            session.add(topic)
        session.commit()

        # Refresh to get IDs
        for name, topic in all_topics.items():
            session.refresh(topic)

        # 4. Create DSA Prerequisite Links
        dsa_links = [
            TopicPrerequisiteLink(topic_id=dsa_topics["Sliding Window"].id, prerequisite_id=dsa_topics["Arrays"].id),
            TopicPrerequisiteLink(topic_id=dsa_topics["Binary Search"].id, prerequisite_id=dsa_topics["Arrays"].id),
            TopicPrerequisiteLink(topic_id=dsa_topics["Heap"].id, prerequisite_id=dsa_topics["Binary Search"].id),
            TopicPrerequisiteLink(topic_id=dsa_topics["Union Find"].id, prerequisite_id=dsa_topics["Graphs"].id),
            TopicPrerequisiteLink(topic_id=dsa_topics["Dynamic Programming"].id, prerequisite_id=dsa_topics["Graphs"].id),
            TopicPrerequisiteLink(topic_id=dsa_topics["Dynamic Programming"].id, prerequisite_id=dsa_topics["Trie"].id),
        ]

        # 5. Cross-Domain Links (Python/System Design → DSA)
        cross_links = [
            TopicPrerequisiteLink(topic_id=sysdesign_topics["Python Concurrency"].id, prerequisite_id=sysdesign_topics["Python Functions"].id),
            TopicPrerequisiteLink(topic_id=sysdesign_topics["Caching"].id, prerequisite_id=dsa_topics["Trie"].id),
            TopicPrerequisiteLink(topic_id=sysdesign_topics["Database Sharding"].id, prerequisite_id=sysdesign_topics["Load Balancers"].id),
        ]

        for link in [*dsa_links, *cross_links]:
            session.add(link)

        # 6. Seed default knowledge nodes for demo user
        demo_nodes = [
            KnowledgeNode(user_id=default_user.id, topic_id=dsa_topics["Arrays"].id, fsrs_stability=12.0, fsrs_difficulty=3.0, last_review=datetime.utcnow() - timedelta(days=2), practice_count=15),
            KnowledgeNode(user_id=default_user.id, topic_id=dsa_topics["Binary Search"].id, fsrs_stability=6.0, fsrs_difficulty=4.5, last_review=datetime.utcnow() - timedelta(days=1), practice_count=8),
            KnowledgeNode(user_id=default_user.id, topic_id=dsa_topics["Graphs"].id, fsrs_stability=4.0, fsrs_difficulty=6.0, last_review=datetime.utcnow() - timedelta(days=3), practice_count=5),
            KnowledgeNode(user_id=default_user.id, topic_id=dsa_topics["Trie"].id, fsrs_stability=2.0, fsrs_difficulty=7.0, last_review=datetime.utcnow() - timedelta(days=5), practice_count=2),
            KnowledgeNode(user_id=default_user.id, topic_id=dsa_topics["Dynamic Programming"].id, fsrs_stability=1.5, fsrs_difficulty=8.5, last_review=datetime.utcnow() - timedelta(days=1), practice_count=4),
        ]
        for node in demo_nodes:
            session.add(node)

        remaining_topics = ["Sliding Window", "Heap", "Union Find"]
        for r_topic in remaining_topics:
            session.add(KnowledgeNode(
                user_id=default_user.id,
                topic_id=dsa_topics[r_topic].id,
                fsrs_stability=2.0,
                fsrs_difficulty=5.0,
                last_review=datetime.utcnow() - timedelta(days=5),
                practice_count=0
            ))

        # System Design topics — fresh start
        for r_topic in ["Python Functions", "Python Concurrency", "Load Balancers", "Caching", "Database Sharding"]:
            session.add(KnowledgeNode(
                user_id=default_user.id,
                topic_id=sysdesign_topics[r_topic].id,
                fsrs_stability=1.0,
                fsrs_difficulty=6.0,
                last_review=datetime.utcnow() - timedelta(days=7),
                practice_count=0
            ))

        # 7. Seed default SyncSources for demo user (all in mock mode)
        for platform in ["leetcode", "github", "codeforces"]:
            session.add(SyncSource(
                user_id=default_user.id,
                platform=platform,
                status="active",
                auth_token="mock"
            ))

        # 8. Seed a mock CalendarConnection for demo user
        session.add(CalendarConnection(
            user_id=default_user.id,
            provider="google",
            auth_token="mock"
        ))

        session.commit()
        logger.info("Database seeding successfully completed!")

# --- USER ENDPOINTS ---

@app.get("/api/users/current")
def get_current_user(session: Session = Depends(get_session)):
    """Simple helper to return our demo user."""
    stmt = select(User).where(User.email == "navya@recallai.io")
    user = session.exec(stmt).first()
    if not user:
        raise HTTPException(status_code=404, detail="Demo user not found.")
    return user

@app.post("/api/users/{user_id}/seed")
def seed_user_confidence(user_id: str, ratings: Dict[str, float], session: Session = Depends(get_session)):
    """
    Cold start endpoint: Seeds a user's initial FSRS parameters based on
    a self-assessment (dictionary of topic_name -> rating between 1 and 5).
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for topic_name, rating in ratings.items():
        topic_stmt = select(Topic).where(Topic.name == topic_name)
        topic = session.exec(topic_stmt).first()
        if not topic:
            continue
            
        stability = max(1.0, (rating - 1.0) * 3.0 + 1.0)
        difficulty = max(1.0, 10.0 - (rating * 1.8))
        
        node_stmt = select(KnowledgeNode).where(
            and_(KnowledgeNode.user_id == user_id, KnowledgeNode.topic_id == topic.id)
        )
        node = session.exec(node_stmt).first()
        if node:
            node.fsrs_stability = stability
            node.fsrs_difficulty = difficulty
            node.last_review = datetime.utcnow()
        else:
            node = KnowledgeNode(
                user_id=user_id,
                topic_id=topic.id,
                fsrs_stability=stability,
                fsrs_difficulty=difficulty,
                last_review=datetime.utcnow() - timedelta(days=1),
                practice_count=1
            )
            session.add(node)
            
    session.commit()
    return {"status": "success", "message": "Knowledge graph seeded with cold-start preferences."}

@app.get("/api/users/{user_id}/plan")
async def get_study_plan(user_id: str, time_override: Optional[int] = None, session: Session = Depends(get_session)):
    """Triggers the planning agent loop to produce a study guide schedule."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await run_planning_agent(session, user_id, time_override)
    return result

@app.post("/api/users/{user_id}/event")
def log_learning_event(user_id: str, event_data: Dict[str, Any], session: Session = Depends(get_session)):
    """
    Logs a new study event and updates FSRS memory engine parameters (stability, difficulty).
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    topic_name = event_data.get("topic_name")
    topic_stmt = select(Topic).where(Topic.name == topic_name)
    topic = session.exec(topic_stmt).first()
    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_name}' not found")
        
    difficulty_rating = event_data.get("difficulty")  # "AGAIN", "HARD", "GOOD", "EASY"
    duration = int(event_data.get("duration_min", 15))
    mistakes = int(event_data.get("mistakes", 0))
    
    new_event = LearningEvent(
        user_id=user_id,
        topic_id=topic.id,
        difficulty=difficulty_rating,
        duration_min=duration,
        mistakes=mistakes,
        timestamp=datetime.utcnow()
    )
    session.add(new_event)
    
    node_stmt = select(KnowledgeNode).where(
        and_(KnowledgeNode.user_id == user_id, KnowledgeNode.topic_id == topic.id)
    )
    node = session.exec(node_stmt).first()
    
    if not node:
        node = KnowledgeNode(
            user_id=user_id,
            topic_id=topic.id,
            fsrs_stability=2.0,
            fsrs_difficulty=5.0,
            last_review=datetime.utcnow(),
            practice_count=0
        )
        session.add(node)
        
    new_s, new_d = update_fsrs_parameters(node.fsrs_stability, node.fsrs_difficulty, difficulty_rating, 1.0)
    node.fsrs_stability = new_s
    node.fsrs_difficulty = new_d
    node.last_review = datetime.utcnow()
    node.practice_count += 1
    
    session.commit()
    session.refresh(node)
    
    ret = calculate_retrievability(node.fsrs_stability, node.last_review)
    return {
        "status": "success",
        "topic": topic.name,
        "new_stability": node.fsrs_stability,
        "new_difficulty": node.fsrs_difficulty,
        "retrievability": round(ret, 4),
        "forgetting_risk": round(1.0 - ret, 4)
    }

@app.get("/api/users/{user_id}/graph")
def get_user_graph_state(user_id: str, session: Session = Depends(get_session)):
    """
    Returns the topics and linkages mapped to React Flow structures,
    incorporating the real FSRS retrievability score of each node to support color mapping.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    topics = session.exec(select(Topic)).all()
    links = session.exec(select(TopicPrerequisiteLink)).all()
    
    nodes_stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    knowledge_nodes = session.exec(nodes_stmt).all()
    kn_map = {n.topic_id: n for n in knowledge_nodes}
    
    formatted_nodes = []
    for topic in topics:
        kn = kn_map.get(topic.id)
        if kn:
            ret = calculate_retrievability(kn.fsrs_stability, kn.last_review)
            stability = kn.fsrs_stability
            difficulty = kn.fsrs_difficulty
            last_review_str = kn.last_review.isoformat()
            practice_count = kn.practice_count
        else:
            ret = 1.0
            stability = 2.0
            difficulty = 5.0
            last_review_str = datetime.utcnow().isoformat()
            practice_count = 0
            
        forgetting_risk = round(1.0 - ret, 4)
        
        formatted_nodes.append({
            "id": topic.name,
            "topic_id": topic.id,
            "description": topic.description,
            "stability": stability,
            "difficulty": difficulty,
            "retrievability": round(ret, 4),
            "forgetting_risk": forgetting_risk,
            "last_review": last_review_str,
            "practice_count": practice_count
        })
        
    formatted_edges = []
    id_to_name = {t.id: t.name for t in topics}
    for idx, link in enumerate(links):
        source = id_to_name.get(link.prerequisite_id)
        target = id_to_name.get(link.topic_id)
        if source and target:
            formatted_edges.append({
                "id": f"edge-{idx}",
                "source": source,
                "target": target
            })
            
    return {
        "nodes": formatted_nodes,
        "edges": formatted_edges
    }

@app.get("/api/users/{user_id}/stats")
def get_user_stats(user_id: str, session: Session = Depends(get_session)):
    """Calculates general stats (average retrievability/health, active logs, count)."""
    stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    nodes = session.exec(stmt).all()
    
    if not nodes:
        return {"health_score": 100, "decayed_topics_count": 0, "logs_count": 0}
        
    total_ret = 0.0
    decayed_count = 0
    for node in nodes:
        ret = calculate_retrievability(node.fsrs_stability, node.last_review)
        total_ret += ret
        if (1.0 - ret) > 0.20:
            decayed_count += 1
            
    avg_ret = total_ret / len(nodes)
    health_score = int(avg_ret * 100)
    
    log_stmt = select(AgentLog).where(AgentLog.user_id == user_id).order_by(AgentLog.timestamp.desc()).limit(5)
    logs = session.exec(log_stmt).all()
    
    return {
        "health_score": health_score,
        "decayed_topics_count": decayed_count,
        "nodes_count": len(nodes),
        "recent_logs": [
            {
                "id": l.id,
                "timestamp": l.timestamp.isoformat(),
                "plan": l.final_plan,
                "reasoning": l.reasoning
            }
            for l in logs
        ]
    }

@app.post("/api/users/{user_id}/simulate-inactivity")
def simulate_inactivity(user_id: str, days: int = Query(default=14), session: Session = Depends(get_session)):
    """
    RE-ACTIVATION SIMULATOR (Core Wow Factor).
    Sets last_review date of all knowledge nodes backward in time by X days,
    triggering sudden FSRS retrievability decay.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    nodes = session.exec(stmt).all()
    
    for node in nodes:
        node.last_review = node.last_review - timedelta(days=days)
        
    session.commit()
    return {
        "status": "success",
        "message": f"Time-traveled {days} days into the future! Check forgetting metrics now."
    }

@app.get("/api/users/{user_id}/decay-alert")
def check_decay_alert(user_id: str, session: Session = Depends(get_session)):
    """
    Checks if active decay alerts are warranted (inactivity > 7 days or health < 80%).
    Returns the alert content matching the Section 12 PRD specification.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    nodes = session.exec(stmt).all()
    
    if not nodes:
        return {"trigger": False}
        
    total_ret = 0.0
    decayed_topics = []
    
    most_recent_review = max(node.last_review for node in nodes)
    days_inactive = (datetime.utcnow() - most_recent_review).days
    
    for node in nodes:
        ret = calculate_retrievability(node.fsrs_stability, node.last_review)
        total_ret += ret
        if (1.0 - ret) > 0.20:
            topic = session.get(Topic, node.topic_id)
            if topic:
                decayed_topics.append({
                    "name": topic.name,
                    "risk": round((1.0 - ret) * 100, 1)
                })
                
    avg_ret = total_ret / len(nodes)
    current_health = int(avg_ret * 100)
    
    trigger_alert = days_inactive >= 7 or current_health < 82
    
    decayed_topics.sort(key=lambda x: x["risk"], reverse=True)
    
    return {
        "trigger": trigger_alert,
        "days_inactive": days_inactive,
        "current_health": current_health,
        "previous_health": min(95, max(85, current_health + int(days_inactive * 1.5))),
        "decayed_topics": [dt["name"] for dt in decayed_topics[:3]],
        "estimated_review_time_min": max(15, len(decayed_topics) * 20)
    }

@app.post("/api/users/{user_id}/coach/chat")
async def coach_chat(user_id: str, chat_input: Dict[str, str], session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    msg = chat_input.get("message", "")
    result = await run_coach_agent(session, user_id, msg)
    return result

# --- AGENT TRACE ENDPOINTS ---

@app.get("/api/users/{user_id}/agent-logs")
def list_agent_logs(user_id: str, limit: int = Query(default=20), session: Session = Depends(get_session)):
    """Lists past agent planning run traces (most recent first)."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    stmt = select(AgentLog).where(AgentLog.user_id == user_id).order_by(AgentLog.timestamp.desc()).limit(limit)
    logs = session.exec(stmt).all()
    return [
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat(),
            "reasoning": l.reasoning,
            "tool_call_count": len(l.tool_calls.get("trace", [])),
            "session_count": len(l.final_plan.get("sessions", []))
        }
        for l in logs
    ]

@app.get("/api/users/{user_id}/agent-logs/{log_id}")
def get_agent_log(user_id: str, log_id: str, session: Session = Depends(get_session)):
    """Retrieves the full detailed reasoning trace for a specific agent planning run."""
    log = session.get(AgentLog, log_id)
    if not log or log.user_id != user_id:
        raise HTTPException(status_code=404, detail="Agent log not found")
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat(),
        "reasoning": log.reasoning,
        "final_plan": log.final_plan,
        "trace": log.tool_calls.get("trace", []),
        "calendar_context": log.calendar_context,
        "deadline_context": log.deadline_context,
    }

# --- SYNC SOURCE ENDPOINTS ---

@app.get("/api/users/{user_id}/sync-sources")
def list_sync_sources(user_id: str, session: Session = Depends(get_session)):
    """Lists all platform sync sources for the user."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    stmt = select(SyncSource).where(SyncSource.user_id == user_id)
    sources = session.exec(stmt).all()
    return [
        {
            "id": s.id,
            "platform": s.platform,
            "status": s.status,
            "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None
        }
        for s in sources
    ]

@app.post("/api/users/{user_id}/sync-sources")
def create_sync_source(user_id: str, source_data: Dict[str, str], session: Session = Depends(get_session)):
    """Connects a new platform (LeetCode, GitHub, Codeforces) for the user."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    platform = source_data.get("platform", "").lower()
    registered = SyncRegistry.list_platforms()
    if platform not in registered:
        raise HTTPException(status_code=400, detail=f"Platform '{platform}' is not supported. Supported: {registered}")

    credential = source_data.get("credential", "mock")
    source = SyncSource(
        user_id=user_id,
        platform=platform,
        status="active",
        auth_token=credential
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return {"id": source.id, "platform": source.platform, "status": source.status}

@app.post("/api/users/{user_id}/sync-sources/{source_id}/sync")
async def trigger_manual_sync(user_id: str, source_id: str, session: Session = Depends(get_session)):
    """Manually triggers a sync for a specific platform source."""
    source = session.get(SyncSource, source_id)
    if not source or source.user_id != user_id:
        raise HTTPException(status_code=404, detail="Sync source not found")
    count = await sync_source_now(session, source)
    return {"status": "success", "events_synced": count}

@app.delete("/api/users/{user_id}/sync-sources/{source_id}")
def disconnect_sync_source(user_id: str, source_id: str, session: Session = Depends(get_session)):
    """Disconnects a platform sync source."""
    source = session.get(SyncSource, source_id)
    if not source or source.user_id != user_id:
        raise HTTPException(status_code=404, detail="Sync source not found")
    source.status = "disconnected"
    session.add(source)
    session.commit()
    return {"status": "disconnected"}

# --- ANALYTICS ENDPOINT ---

@app.get("/api/users/{user_id}/analytics")
def get_analytics(user_id: str, session: Session = Depends(get_session)):
    """
    Computes analytics stats including:
    - Retention score trend (per-topic FSRS retrievability)
    - Platform sync health (each source status & last sync)
    - Practice accuracy rates by topic (based on LearningEvent records)
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. Knowledge node retention stats
    nodes_stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    nodes = session.exec(nodes_stmt).all()
    retention_data = []
    for node in nodes:
        topic = session.get(Topic, node.topic_id)
        if not topic:
            continue
        ret = calculate_retrievability(node.fsrs_stability, node.last_review)
        retention_data.append({
            "topic": topic.name,
            "retrievability": round(ret, 4),
            "forgetting_risk": round(1.0 - ret, 4),
            "stability": node.fsrs_stability,
            "difficulty": node.fsrs_difficulty,
            "practice_count": node.practice_count,
            "last_review": node.last_review.isoformat()
        })
    retention_data.sort(key=lambda x: x["forgetting_risk"], reverse=True)

    # 2. Per-topic accuracy
    events_stmt = select(LearningEvent).where(LearningEvent.user_id == user_id)
    events = session.exec(events_stmt).all()
    topic_accuracy: Dict[str, Dict[str, int]] = {}
    for ev in events:
        topic = session.get(Topic, ev.topic_id)
        if not topic:
            continue
        if topic.name not in topic_accuracy:
            topic_accuracy[topic.name] = {"total": 0, "success": 0}
        topic_accuracy[topic.name]["total"] += 1
        if ev.difficulty.upper() != "AGAIN":
            topic_accuracy[topic.name]["success"] += 1

    accuracy_data = [
        {
            "topic": name,
            "total_attempts": data["total"],
            "success_rate": round(data["success"] / data["total"], 4) if data["total"] > 0 else 0.0
        }
        for name, data in topic_accuracy.items()
    ]

    # 3. Platform sync health
    sources_stmt = select(SyncSource).where(SyncSource.user_id == user_id)
    sources = session.exec(sources_stmt).all()
    sync_health = [
        {
            "id": s.id,
            "platform": s.platform,
            "status": s.status,
            "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None,
            "events_count": session.exec(
                select(RawSyncEvent).where(RawSyncEvent.sync_source_id == s.id)
            ).all().__len__()
        }
        for s in sources
    ]

    # 4. Summary
    total_nodes = len(nodes)
    avg_ret = sum(r["retrievability"] for r in retention_data) / total_nodes if total_nodes > 0 else 1.0

    return {
        "overall_health": round(avg_ret * 100, 1),
        "total_topics": total_nodes,
        "retention_breakdown": retention_data,
        "accuracy_by_topic": accuracy_data,
        "sync_health": sync_health
    }

# --- CALENDAR ENDPOINTS ---

@app.get("/api/users/{user_id}/calendar/connection")
def get_calendar_connection(user_id: str, session: Session = Depends(get_session)):
    """Returns calendar connection status for the user."""
    stmt = select(CalendarConnection).where(CalendarConnection.user_id == user_id)
    conn = session.exec(stmt).first()
    if not conn:
        return {"connected": False}
    return {"connected": True, "provider": conn.provider, "last_synced_at": conn.last_synced_at}

@app.post("/api/users/{user_id}/calendar/connection")
def create_calendar_connection(user_id: str, data: Dict[str, str], session: Session = Depends(get_session)):
    """Creates or updates a Google Calendar connection (mock or real OAuth token JSON)."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    stmt = select(CalendarConnection).where(CalendarConnection.user_id == user_id)
    conn = session.exec(stmt).first()
    if conn:
        conn.auth_token = data.get("auth_token", "mock")
        conn.last_synced_at = datetime.utcnow()
    else:
        conn = CalendarConnection(
            user_id=user_id,
            provider=data.get("provider", "google"),
            auth_token=data.get("auth_token", "mock"),
            last_synced_at=datetime.utcnow()
        )
        session.add(conn)
    session.commit()
    return {"status": "connected", "provider": conn.provider}

# --- API KEY AUTH (browser extension) ---

def get_api_key_user(
    x_api_key: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Resolves the user behind an extension telemetry request via the X-API-Key header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    key = session.exec(
        select(ApiKey).where(and_(ApiKey.key == x_api_key, ApiKey.revoked == False))  # noqa: E712
    ).first()
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    user = session.get(User, key.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="API key is not attached to a user")
    key.last_used_at = datetime.utcnow()
    session.add(key)
    session.commit()
    return user

@app.post("/api/users/{user_id}/api-keys")
def create_api_key(user_id: str, data: Optional[Dict[str, str]] = None, session: Session = Depends(get_session)):
    """Issues a new API key the browser extension uses to post solve telemetry."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    key = ApiKey(user_id=user_id, label=(data or {}).get("label", "browser-extension"))
    session.add(key)
    session.commit()
    session.refresh(key)
    # Full key is only ever returned once, at creation time.
    return {"id": key.id, "key": key.key, "label": key.label, "created_at": key.created_at.isoformat()}

@app.get("/api/users/{user_id}/api-keys")
def list_api_keys(user_id: str, session: Session = Depends(get_session)):
    """Lists the user's API keys (masked; the full secret is shown only at creation)."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    keys = session.exec(select(ApiKey).where(ApiKey.user_id == user_id)).all()
    return [
        {
            "id": k.id,
            "label": k.label,
            "masked_key": f"{k.key[:8]}…{k.key[-4:]}",
            "created_at": k.created_at.isoformat(),
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "revoked": k.revoked,
        }
        for k in keys
    ]

# --- TELEMETRY (personalized memory model) ---

@app.post("/api/telemetry/solve")
def post_solve_telemetry(
    payload: Dict[str, Any],
    user: User = Depends(get_api_key_user),
    session: Session = Depends(get_session),
):
    """
    Records a solve captured by the browser extension and updates the user's
    personalized memory model. Auth via X-API-Key header.

    Expected payload:
      platform, platform_problem_id (required); title, url, difficulty, topic_tags,
      opened_at, first_keystroke_at, submitted_at,
      time_to_understand_s, time_to_write_s, num_submissions, hints_used, verdict, source
    """
    if not payload.get("platform") or not payload.get("platform_problem_id"):
        raise HTTPException(status_code=422, detail="platform and platform_problem_id are required")
    return ingest_solve(session, user, payload)

@app.get("/api/users/{user_id}/revision-queue")
async def get_revision_queue(user_id: str, session: Session = Depends(get_session)):
    """
    The core output: topics ranked by how urgently the user should revise them,
    using their personalized forgetting curve, prerequisite structure, and calendar
    deadlines. Each topic carries the problems the user has actually solved for it.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    params = session.get(UserMemoryParams, user_id)
    decay = params.decay_exponent if params else DEFAULT_DECAY_EXPONENT

    nodes = session.exec(select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)).all()
    topic_map = {t.id: t for t in session.exec(select(Topic)).all()}

    # 1. Forgetting risk per topic under the user's own decay exponent.
    risk_by_topic: Dict[str, float] = {}
    node_by_topic: Dict[str, KnowledgeNode] = {}
    for node in nodes:
        topic = topic_map.get(node.topic_id)
        if not topic:
            continue
        r = predict_retrievability(node.fsrs_stability, node.last_review, decay)
        risk_by_topic[topic.name] = round(1.0 - r, 4)
        node_by_topic[topic.name] = node

    # 2. Deadline urgency from the calendar.
    cal = session.exec(select(CalendarConnection).where(CalendarConnection.user_id == user_id)).first()
    deadlines = await get_upcoming_deadlines(cal.auth_token if cal else "mock")
    urgency_by_topic: Dict[str, float] = {}
    for dl in deadlines:
        try:
            days_until = (datetime.fromisoformat(dl["date"]).replace(tzinfo=None) - datetime.utcnow()).days
        except (ValueError, KeyError):
            days_until = 7
        mult = 2.0 if days_until <= 3 else (1.5 if days_until <= 7 else 1.15)
        for t in dl.get("related_topics", []):
            urgency_by_topic[t] = max(urgency_by_topic.get(t, 1.0), mult)

    # 3. Problems the user has solved, grouped by topic (most recent first).
    attempts = session.exec(
        select(SolveAttempt).where(SolveAttempt.user_id == user_id).order_by(SolveAttempt.submitted_at.desc())
    ).all()
    problems_by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for a in attempts:
        prob = session.get(Problem, a.problem_id)
        if not prob:
            continue
        for t in prob.topics:
            bucket = problems_by_topic.setdefault(t.name, [])
            if len(bucket) < 3 and all(p["id"] != prob.id for p in bucket):
                bucket.append({
                    "id": prob.id, "title": prob.title or prob.platform_problem_id,
                    "url": prob.url, "platform": prob.platform,
                    "last_recall_strength": a.recall_strength,
                })

    # 4. Priority with prerequisite boosting (weak dependents raise a topic's importance).
    queue = []
    for topic_name, risk in risk_by_topic.items():
        weak_dependents = sum(
            1 for dep in get_all_reachable_dependents(session, topic_name)
            if risk_by_topic.get(dep, 0.0) > 0.20
        )
        importance = prerequisite_boost(1.0, weak_dependents)
        urgency = urgency_by_topic.get(topic_name, 1.0)
        node = node_by_topic[topic_name]
        queue.append({
            "topic": topic_name,
            "priority": revision_priority(risk, importance, urgency),
            "forgetting_risk": risk,
            "stability_days": node.fsrs_stability,
            "difficulty": node.fsrs_difficulty,
            "practice_count": node.practice_count,
            "last_review": node.last_review.isoformat(),
            "deadline_driven": topic_name in urgency_by_topic,
            "reinforces_weak_dependents": weak_dependents,
            "problems": problems_by_topic.get(topic_name, []),
        })

    queue.sort(key=lambda x: x["priority"], reverse=True)
    return {
        "decay_exponent": decay,
        "personalized": bool(params and params.attempts_observed >= 8),
        "attempts_observed": params.attempts_observed if params else 0,
        "queue": queue,
    }

@app.get("/api/users/{user_id}/solve-attempts")
def list_solve_attempts(user_id: str, limit: int = Query(default=25), session: Session = Depends(get_session)):
    """Recent solve telemetry (understand vs. write time, attempts, derived recall) — most recent first."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    stmt = (
        select(SolveAttempt).where(SolveAttempt.user_id == user_id)
        .order_by(SolveAttempt.submitted_at.desc()).limit(limit)
    )
    attempts = session.exec(stmt).all()
    out = []
    for a in attempts:
        prob = session.get(Problem, a.problem_id)
        out.append({
            "id": a.id,
            "problem": (prob.title or prob.platform_problem_id) if prob else None,
            "platform": prob.platform if prob else None,
            "difficulty": prob.difficulty if prob else None,
            "time_to_understand_s": a.time_to_understand_s,
            "time_to_write_s": a.time_to_write_s,
            "num_submissions": a.num_submissions,
            "hints_used": a.hints_used,
            "verdict": a.verdict,
            "recall_strength": a.recall_strength,
            "perceived_difficulty": a.perceived_difficulty,
            "source": a.source,
            "submitted_at": a.submitted_at.isoformat(),
        })
    return out
