import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, and_

from .models import (
    create_db_and_tables, get_session, User, Topic, LearningEvent, 
    KnowledgeNode, AgentLog, TopicPrerequisiteLink, engine
)
from .fsrs import calculate_retrievability, update_fsrs_parameters
from .graph_utils import get_related_concepts
from .agent import run_planning_agent, run_coach_agent

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="RecallAI - Spaced Repetition Agent Backend", version="1.0.0")

# CORS middleware for Next.js frontend calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup DB setup and auto-seeding
@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    seed_dsa_data()

def seed_dsa_data():
    """Seeds default user, topics, and dependency links if database is empty."""
    with Session(engine) as session:
        # Check if topics exist
        existing_topics = session.exec(select(Topic)).all()
        if existing_topics:
            logger.info("Database already seeded.")
            return

        logger.info("Seeding database with default DSA topics and relationships...")
        # 1. Create default User
        default_user = User(
            id="demo-user-id",
            name="Navya",
            email="navya@recallai.io",
            preferences={"dailyStudyTimeMinutes": 120}
        )
        session.add(default_user)

        # 2. Create DSA Topics
        topics = {
            "Arrays": Topic(name="Arrays", description="Basic array manipulations, two pointers, prefix sums"),
            "Sliding Window": Topic(name="Sliding Window", description="Subarray constraints, variable and fixed size window algorithms"),
            "Binary Search": Topic(name="Binary Search", description="Divide and conquer, searching sorted spaces, search by answer"),
            "Heap": Topic(name="Heap", description="Priority queues, top K elements, heap sort"),
            "Trie": Topic(name="Trie", description="Prefix tree structures, word insert/search/prefix matches"),
            "Graphs": Topic(name="Graphs", description="Representations, BFS, DFS, shortest path algorithms"),
            "Union Find": Topic(name="Union Find", description="Disjoint set data structures, path compression, union by rank"),
            "Dynamic Programming": Topic(name="Dynamic Programming", description="Memoization, tabulation, state machines, knapsack problems")
        }
        for topic in topics.values():
            session.add(topic)
        session.commit()

        # Refresh to get IDs
        for name, topic in topics.items():
            session.refresh(topic)

        # 3. Create Prerequisite Links
        links = [
            TopicPrerequisiteLink(topic_id=topics["Sliding Window"].id, prerequisite_id=topics["Arrays"].id),
            TopicPrerequisiteLink(topic_id=topics["Binary Search"].id, prerequisite_id=topics["Arrays"].id),
            TopicPrerequisiteLink(topic_id=topics["Heap"].id, prerequisite_id=topics["Binary Search"].id),
            TopicPrerequisiteLink(topic_id=topics["Union Find"].id, prerequisite_id=topics["Graphs"].id),
            TopicPrerequisiteLink(topic_id=topics["Dynamic Programming"].id, prerequisite_id=topics["Graphs"].id),
            TopicPrerequisiteLink(topic_id=topics["Dynamic Programming"].id, prerequisite_id=topics["Trie"].id)
        ]
        for link in links:
            session.add(link)
        
        # 4. Seed default knowledge nodes for demo user (low baseline, assuming they know some arrays/graphs)
        demo_nodes = [
            KnowledgeNode(user_id=default_user.id, topic_id=topics["Arrays"].id, fsrs_stability=12.0, fsrs_difficulty=3.0, last_review=datetime.utcnow() - timedelta(days=2), practice_count=15),
            KnowledgeNode(user_id=default_user.id, topic_id=topics["Binary Search"].id, fsrs_stability=6.0, fsrs_difficulty=4.5, last_review=datetime.utcnow() - timedelta(days=1), practice_count=8),
            KnowledgeNode(user_id=default_user.id, topic_id=topics["Graphs"].id, fsrs_stability=4.0, fsrs_difficulty=6.0, last_review=datetime.utcnow() - timedelta(days=3), practice_count=5),
            KnowledgeNode(user_id=default_user.id, topic_id=topics["Trie"].id, fsrs_stability=2.0, fsrs_difficulty=7.0, last_review=datetime.utcnow() - timedelta(days=5), practice_count=2),
            KnowledgeNode(user_id=default_user.id, topic_id=topics["Dynamic Programming"].id, fsrs_stability=1.5, fsrs_difficulty=8.5, last_review=datetime.utcnow() - timedelta(days=1), practice_count=4)
        ]
        for node in demo_nodes:
            session.add(node)

        # Seed other topics with initial settings
        remaining_topics = ["Sliding Window", "Heap", "Union Find"]
        for r_topic in remaining_topics:
            session.add(KnowledgeNode(
                user_id=default_user.id,
                topic_id=topics[r_topic].id,
                fsrs_stability=2.0,
                fsrs_difficulty=5.0,
                last_review=datetime.utcnow() - timedelta(days=5),
                practice_count=0
            ))
            
        session.commit()
        logger.info("Database seeding successfully completed!")

# --- ENDPOINTS ---

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
            
        # Map 1-5 rating to starting parameters
        # 1 (low confidence) -> Low stability (e.g. 1.0 day), High difficulty (8.0)
        # 5 (high confidence) -> High stability (e.g. 14.0 days), Low difficulty (2.0)
        stability = max(1.0, (rating - 1.0) * 3.0 + 1.0)
        difficulty = max(1.0, 10.0 - (rating * 1.8))
        
        # Check if node exists
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
        
    difficulty_rating = event_data.get("difficulty") # "AGAIN", "HARD", "GOOD", "EASY"
    duration = int(event_data.get("duration_min", 15))
    mistakes = int(event_data.get("mistakes", 0))
    
    # Save the learning event
    new_event = LearningEvent(
        user_id=user_id,
        topic_id=topic.id,
        difficulty=difficulty_rating,
        duration_min=duration,
        mistakes=mistakes,
        timestamp=datetime.utcnow()
    )
    session.add(new_event)
    
    # Fetch and update FSRS parameters
    node_stmt = select(KnowledgeNode).where(
        and_(KnowledgeNode.user_id == user_id, KnowledgeNode.topic_id == topic.id)
    )
    node = session.exec(node_stmt).first()
    
    if not node:
        # Create default
        node = KnowledgeNode(
            user_id=user_id,
            topic_id=topic.id,
            fsrs_stability=2.0,
            fsrs_difficulty=5.0,
            last_review=datetime.utcnow(),
            practice_count=0
        )
        session.add(node)
        
    new_s, new_d = update_fsrs_parameters(node.fsrs_stability, node.fsrs_difficulty, difficulty_rating)
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
    
    # Load knowledge nodes mapping
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
            # Fallback/Default
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
    # Map topic IDs to names for React Flow references
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
    # 1. Fetch nodes
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
    
    # Get last logs
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
        
    # Calculate health score before/after simulation
    total_ret = 0.0
    decayed_topics = []
    
    # Estimate a theoretical pre-decay health (e.g. 91% if they left in a good state)
    # If they actually had a last_review far away, the current retrievability will show decay.
    most_recent_review = max(node.last_review for node in nodes)
    days_inactive = (datetime.utcnow() - most_recent_review).days
    
    for node in nodes:
        ret = calculate_retrievability(node.fsrs_stability, node.last_review)
        total_ret += ret
        # Filter decayed topics
        if (1.0 - ret) > 0.20:
            topic = session.get(Topic, node.topic_id)
            if topic:
                decayed_topics.append({
                    "name": topic.name,
                    "risk": round((1.0 - ret) * 100, 1)
                })
                
    avg_ret = total_ret / len(nodes)
    current_health = int(avg_ret * 100)
    
    # We trigger the alert if they have been away for more than 7 days, or health has fallen significantly.
    trigger_alert = days_inactive >= 7 or current_health < 82
    
    # Sort decayed topics by risk descending
    decayed_topics.sort(key=lambda x: x["risk"], reverse=True)
    
    return {
        "trigger": trigger_alert,
        "days_inactive": days_inactive,
        "current_health": current_health,
        # Display simulated baseline drop
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
