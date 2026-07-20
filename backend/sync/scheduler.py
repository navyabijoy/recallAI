import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select, and_
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..models import User, SyncSource, RawSyncEvent, LearningEvent, KnowledgeNode, Topic, engine
from .base import SyncRegistry
from ..fsrs import update_fsrs_parameters

# Ensure adapters are registered by importing them
from . import leetcode, github, codeforces  # noqa: F401

logger = logging.getLogger(__name__)

# Set up the scheduler
scheduler = AsyncIOScheduler()

def get_platform_weight(platform: str) -> float:
    """Returns the FSRS confidence weight for a platform."""
    if platform == "github":
        return 0.3
    elif platform == "leetcode" or platform == "codeforces":
        return 1.0
    return 0.6  # Default weight for other platforms

def get_fsrs_rating(platform: str, event: Dict[str, Any]) -> str:
    """Determines the FSRS difficulty rating ('AGAIN', 'HARD', 'GOOD', 'EASY') based on event status."""
    payload = event.get("raw_payload", {})
    if platform == "leetcode":
        status = payload.get("status")
        if status == "Accepted":
            # Map based on LeetCode difficulty
            diff = payload.get("difficulty", "Medium")
            if diff == "Easy":
                return "EASY"
            elif diff == "Medium":
                return "GOOD"
            else:
                return "HARD"
        else:
            return "AGAIN"
            
    elif platform == "codeforces":
        verdict = payload.get("verdict")
        if verdict == "OK":
            rating = payload.get("problem_rating")
            if rating and rating < 1200:
                return "EASY"
            elif rating and rating < 1700:
                return "GOOD"
            else:
                return "HARD"
        else:
            return "AGAIN"
            
    elif platform == "github":
        # Commits are positive signal only
        return "GOOD"
        
    return "GOOD"

async def sync_source_now(session: Session, source: SyncSource) -> int:
    """Syncs a single SyncSource, saves events, and updates FSRS knowledge state."""
    platform = source.platform
    logger.info(f"Syncing source {source.id} for user {source.user_id} on platform {platform}...")
    
    try:
        adapter = SyncRegistry.get_adapter(platform)
    except Exception as ex:
        logger.error(f"Failed to find adapter for platform {platform}: {ex}")
        source.status = "error"
        session.add(source)
        session.commit()
        return 0
        
    # Use 'mock' as credential fallback if not provided
    credential = source.auth_token or "mock"
    
    try:
        events = await adapter.sync(credential)
        new_events_count = 0
        
        for event in events:
            event_id = event["event_id"]
            
            # 1. Prevent duplicate processing
            existing_event = session.get(RawSyncEvent, event_id)
            if existing_event:
                continue
                
            # 2. Match mapped topic
            topic_name = event.get("mapped_topic")
            topic = None
            if topic_name:
                topic_stmt = select(Topic).where(Topic.name == topic_name)
                topic = session.exec(topic_stmt).first()
                
            confidence_weight = get_platform_weight(platform)
            processed_at = datetime.utcnow()
            
            # 3. Log LearningEvent and update FSRS if a topic was successfully matched
            if topic:
                rating = get_fsrs_rating(platform, event)
                
                # Check if it's GitHub and rating is AGAIN - we don't trigger decay for absent commits,
                # but if GitHub returns a negative event (unlikely), we still check. We assume GitHub events are positive.
                if platform == "github" and rating == "AGAIN":
                    # Skip FSRS updates for negative Github events
                    pass
                else:
                    # Log learning event
                    learning_event = LearningEvent(
                        user_id=source.user_id,
                        topic_id=topic.id,
                        difficulty=rating,
                        duration_min=15,  # Estimated default practice time
                        mistakes=1 if rating == "AGAIN" else 0,
                        timestamp=datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
                    )
                    session.add(learning_event)
                    
                    # Fetch / Create Knowledge Node
                    node_stmt = select(KnowledgeNode).where(
                        and_(KnowledgeNode.user_id == source.user_id, KnowledgeNode.topic_id == topic.id)
                    )
                    node = session.exec(node_stmt).first()
                    
                    if not node:
                        node = KnowledgeNode(
                            user_id=source.user_id,
                            topic_id=topic.id,
                            fsrs_stability=2.0,
                            fsrs_difficulty=5.0,
                            last_review=datetime.utcnow() - timezone.utc.utcoffset(datetime.utcnow()),
                            practice_count=0
                        )
                        session.add(node)
                        
                    # Calculate new FSRS parameters
                    new_s, new_d = update_fsrs_parameters(
                        node.fsrs_stability, node.fsrs_difficulty, rating, confidence_weight
                    )
                    node.fsrs_stability = new_s
                    node.fsrs_difficulty = new_d
                    node.last_review = datetime.utcnow()
                    node.practice_count += 1
                    session.add(node)
            
            # 4. Save RawSyncEvent
            raw_event = RawSyncEvent(
                id=event_id,
                sync_source_id=source.id,
                raw_payload=event.get("raw_payload", {}),
                mapped_topic_id=topic.id if topic else None,
                confidence_weight=confidence_weight,
                processed_at=processed_at,
                created_at=datetime.utcnow()
            )
            session.add(raw_event)
            new_events_count += 1
            
        # Update SyncSource status
        source.status = "active"
        source.last_synced_at = datetime.utcnow()
        session.add(source)
        session.commit()
        
        logger.info(f"Sync complete for source {source.id}. Synced {new_events_count} new events.")
        return new_events_count
        
    except Exception as e:
        logger.error(f"Error executing sync for source {source.id}: {e}", exc_info=True)
        source.status = "error"
        session.add(source)
        session.commit()
        return 0

async def sync_all_active_sources():
    """Scheduled task to sync all active sync sources across all users."""
    logger.info("Running scheduled sync for all active platforms...")
    with Session(engine) as session:
        sources_stmt = select(SyncSource).where(SyncSource.status != "disconnected")
        sources = session.exec(sources_stmt).all()
        for source in sources:
            await sync_source_now(session, source)

def start_scheduler():
    """Starts the APScheduler background task."""
    if not scheduler.running:
        scheduler.add_job(
            sync_all_active_sources,
            "interval",
            minutes=5,
            id="platform_sync_job",
            replace_existing=True
        )
        scheduler.start()
        logger.info("APScheduler started: Platform synchronization polling active every 5 minutes.")

def shutdown_scheduler():
    """Stops the APScheduler background task."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler background sync scheduler shutdown.")
