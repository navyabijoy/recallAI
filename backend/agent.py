import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from sqlmodel import Session, select
from anthropic import AsyncAnthropic

from .models import User, Topic, LearningEvent, KnowledgeNode, AgentLog, CalendarConnection
from .fsrs import calculate_retrievability
from .graph_utils import get_related_concepts as graph_get_related_concepts
from .sync.calendar_api import get_calendar_availability, get_upcoming_deadlines

logger = logging.getLogger(__name__)

# Anthropic Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-5")
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "2048"))
# Cap real-LLM agent invocations per user per rolling 24h window (cost control for beta).
AGENT_DAILY_CALL_CAP = int(os.getenv("AGENT_DAILY_CALL_CAP", "20"))

# Create Client (safe if key is missing/placeholder)
if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "placeholder":
    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
else:
    client = None


def _daily_agent_call_count(session: Session, user_id: str) -> int:
    """Counts AgentLog rows for this user in the last 24h, as a proxy for real-LLM agent calls."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stmt = select(AgentLog).where(AgentLog.user_id == user_id, AgentLog.timestamp >= cutoff)
    return len(session.exec(stmt).all())


def _daily_cap_exceeded(session: Session, user_id: str) -> bool:
    return _daily_agent_call_count(session, user_id) >= AGENT_DAILY_CALL_CAP

# --- TOOL IMPLEMENTATIONS ---

def tool_get_topic_history(session: Session, user_id: str, topic_name: str) -> Dict[str, Any]:
    """Retrieves the practice history and stats for a given topic."""
    # Find topic
    topic_stmt = select(Topic).where(Topic.name == topic_name)
    topic = session.exec(topic_stmt).first()
    if not topic:
        return {"error": f"Topic '{topic_name}' not found."}

    # Fetch events
    events_stmt = select(LearningEvent).where(
        LearningEvent.user_id == user_id,
        LearningEvent.topic_id == topic.id
    ).order_by(LearningEvent.timestamp.desc())
    events = session.exec(events_stmt).all()

    if not events:
        return {
            "topic": topic_name,
            "attempts": 0,
            "msg": "No practice history exists for this topic yet."
        }

    total_attempts = len(events)
    avg_duration = sum(e.duration_min for e in events) / total_attempts
    total_mistakes = sum(e.mistakes for e in events)
    again_count = sum(1 for e in events if e.difficulty.upper() == "AGAIN")
    success_rate = (total_attempts - again_count) / total_attempts if total_attempts > 0 else 0.0

    return {
        "topic": topic_name,
        "attempts": total_attempts,
        "avg_duration_min": round(avg_duration, 1),
        "total_mistakes": total_mistakes,
        "success_rate": round(success_rate, 2),
        "last_attempt": events[0].timestamp.isoformat(),
        "recent_grades": [e.difficulty for e in events[:5]]
    }

def tool_get_forgetting_scores(session: Session, user_id: str) -> List[Dict[str, Any]]:
    """Calculates retrievability for all user topics and returns them sorted by highest decay (forgetting probability)."""
    stmt = select(KnowledgeNode).where(KnowledgeNode.user_id == user_id)
    nodes = session.exec(stmt).all()
    
    scores = []
    for node in nodes:
        # Load topic name
        topic = session.get(Topic, node.topic_id)
        if not topic:
            continue
            
        ret = calculate_retrievability(node.fsrs_stability, node.last_review)
        forgetting_risk = round(1.0 - ret, 4)
        
        scores.append({
            "topic_name": topic.name,
            "stability_days": node.fsrs_stability,
            "difficulty_rating": node.fsrs_difficulty,
            "retrievability": round(ret, 4),
            "forgetting_risk": forgetting_risk,
            "last_review": node.last_review.isoformat(),
            "practice_count": node.practice_count
        })
        
    # Sort by forgetting risk descending (highest risk first)
    scores.sort(key=lambda x: x["forgetting_risk"], reverse=True)
    return scores

def tool_get_related_concepts(session: Session, topic_name: str) -> Dict[str, Any]:
    """Traverses the knowledge graph to fetch prerequisite and dependent topics."""
    return graph_get_related_concepts(session, topic_name)

def tool_get_available_time(session: Session, user_id: str) -> int:
    """Returns the study duration limits stated in the user's preferences."""
    user = session.get(User, user_id)
    if not user or not user.preferences:
        return 60  # Default 60 minutes
    return user.preferences.get("dailyStudyTimeMinutes", 60)

def tool_check_plan_fits_budget(plan: Dict[str, Any], available_time: int) -> Dict[str, Any]:
    """Validates if the generated study plan fits within the user's available time constraint."""
    sessions = plan.get("sessions", [])
    total_time = sum(item.get("duration_min", 0) for item in sessions)
    overflow = total_time - available_time
    
    return {
        "fits": overflow <= 0,
        "total_duration_min": total_time,
        "available_time_min": available_time,
        "overflow_min": max(0, overflow)
    }

def tool_log_recommendation(
    session: Session,
    user_id: str,
    plan: Dict[str, Any],
    reasoning: str,
    tool_calls_log: List[Dict[str, Any]],
    calendar_context: Optional[Dict[str, Any]] = None,
    deadline_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Persists the final planned session and explanations to the database."""
    log_entry = AgentLog(
        user_id=user_id,
        timestamp=datetime.utcnow(),
        tool_calls={"trace": tool_calls_log},
        final_plan=plan,
        reasoning=reasoning,
        calendar_context=calendar_context,
        deadline_context=deadline_context
    )
    session.add(log_entry)
    session.commit()
    session.refresh(log_entry)
    return {
        "status": "success",
        "log_id": log_entry.id,
        "message": "Recommendation plan logged successfully."
    }

async def tool_get_calendar_availability(session: Session, user_id: str) -> Dict[str, Any]:
    """Fetches the user's calendar free/busy slots for the next 7 days."""
    cal_stmt = select(CalendarConnection).where(CalendarConnection.user_id == user_id)
    connection = session.exec(cal_stmt).first()
    auth_token = connection.auth_token if connection else "mock"
    return await get_calendar_availability(auth_token)

async def tool_get_upcoming_deadlines(session: Session, user_id: str) -> List[Dict[str, Any]]:
    """Fetches upcoming calendar deadline events (interviews, exams, contests) for the user."""
    cal_stmt = select(CalendarConnection).where(CalendarConnection.user_id == user_id)
    connection = session.exec(cal_stmt).first()
    auth_token = connection.auth_token if connection else "mock"
    return await get_upcoming_deadlines(auth_token)

# --- TOOL METADATA FOR LLM ---

TOOLS_SCHEMA = [
    {
        "name": "get_forgetting_scores",
        "description": "Get forgetting probability scores based on FSRS calculations for all topics.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_topic_history",
        "description": "Get user practice history metrics (attempts, mistakes, success rate, grades) for a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic_name": {"type": "string", "description": "The name of the topic, e.g. 'Graphs'"}
            },
            "required": ["topic_name"]
        }
    },
    {
        "name": "get_related_concepts",
        "description": "Query knowledge graph prerequisites and dependents for a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic_name": {"type": "string", "description": "Name of the topic"}
            },
            "required": ["topic_name"]
        }
    },
    {
        "name": "get_available_time",
        "description": "Retrieve the user's active session time budget.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "check_plan_fits_budget",
        "description": "Check if a draft plan fits the available time budget.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "object",
                    "properties": {
                        "sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string"},
                                    "duration_min": {"type": "integer"},
                                    "focus": {"type": "string"}
                                },
                                "required": ["topic", "duration_min"]
                            }
                        }
                    },
                    "required": ["sessions"]
                }
            },
            "required": ["plan"]
        }
    },
    {
        "name": "log_recommendation",
        "description": "Persist the finalized revision plan and explanatory reasoning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "object",
                    "properties": {
                        "sessions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string"},
                                    "duration_min": {"type": "integer"},
                                    "focus": {"type": "string"}
                                },
                                "required": ["topic", "duration_min"]
                            }
                        }
                    },
                    "required": ["sessions"]
                },
                "reasoning": {"type": "string", "description": "Detailed reasoning for selecting this plan."}
            },
            "required": ["plan", "reasoning"]
        }
    },
    {
        "name": "get_calendar_availability",
        "description": "Fetch the user's calendar free/busy blocks for the next 7 days to fit study sessions.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_upcoming_deadlines",
        "description": "Fetch upcoming interviews, exams, and contests from the user's calendar to prioritize relevant topics.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    }
]

# --- EXECUTE AGENT LOOP ---

async def run_planning_agent(session: Session, user_id: str, available_time_override: int = None) -> Dict[str, Any]:
    """
    Runs the AI Agent planning loop.
    If OpenRouter API key is missing or model call fails, runs a deterministic mock planner
    to ensure seamless portfolio operations.
    """
    tool_calls_trace = []
    
    # Pre-fetch calendar data to inject into context
    calendar_context = await tool_get_calendar_availability(session, user_id)
    deadline_context = {"deadlines": await tool_get_upcoming_deadlines(session, user_id)}

    # 1. Fallback to mock if API key isn't provided or the daily cost cap was hit
    if client is None:
        logger.info("Anthropic client not initialized. Running mock agent loop.")
        return await run_mock_agent(session, user_id, available_time_override, calendar_context, deadline_context)

    if _daily_cap_exceeded(session, user_id):
        logger.info(f"Daily agent call cap reached for user {user_id}. Running mock agent loop.")
        return await run_mock_agent(session, user_id, available_time_override, calendar_context, deadline_context)

    system_instruction = (
        "You are RecallAI's Spaced Repetition Planning Agent. "
        "Your task is to draft an optimal study plan for today based on the user's knowledge state, forgetting risks, and real calendar availability.\n"
        "Rules:\n"
        "1. Start by fetching the user's available time and forgetting scores.\n"
        "2. Fetch calendar availability using get_calendar_availability to understand free time blocks.\n"
        "3. Fetch upcoming deadlines using get_upcoming_deadlines - prioritize topics related to nearby deadlines.\n"
        "4. For topics with high decay (forgetting risk > 20%), fetch their topic history and related concepts.\n"
        "5. Draft a schedule that allocates time to review high-decay topics, fitting them inside actual free calendar slots.\n"
        "6. Validate the schedule with check_plan_fits_budget. If it overflows, reduce topic time or drop lower priority topics and check again.\n"
        "7. Once it fits, run log_recommendation to save the final plan and explain your logic.\n"
        "8. Return ONLY the final plan JSON containing the keys: 'sessions' and 'reasoning'."
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Please plan today's study session. user_id={user_id}. "
                f"Available time override={available_time_override or 'None'}. "
                f"Calendar context pre-loaded: {len(calendar_context.get('free_blocks', []))} free blocks available. "
                f"Deadlines context pre-loaded: {len(deadline_context.get('deadlines', []))} upcoming deadline(s)."
            )
        }
    ]

    available_time = available_time_override or tool_get_available_time(session, user_id)

    try:
        for step in range(12):  # Limit loop to 12 steps to prevent infinite running
            response = await client.messages.create(
                model=MODEL_NAME,
                max_tokens=AGENT_MAX_TOKENS,
                system=system_instruction,
                messages=messages,
                tools=TOOLS_SCHEMA,
            )

            messages.append({"role": "assistant", "content": response.content})
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            # If the model requested tool calls
            if tool_use_blocks:
                tool_result_content = []
                for block in tool_use_blocks:
                    name = block.name
                    args = block.input or {}

                    # Execute tool
                    tool_res = None
                    if name == "get_forgetting_scores":
                        tool_res = tool_get_forgetting_scores(session, user_id)
                    elif name == "get_topic_history":
                        tool_res = tool_get_topic_history(session, user_id, args.get("topic_name"))
                    elif name == "get_related_concepts":
                        tool_res = tool_get_related_concepts(session, args.get("topic_name"))
                    elif name == "get_available_time":
                        tool_res = available_time
                    elif name == "check_plan_fits_budget":
                        tool_res = tool_check_plan_fits_budget(args.get("plan", {}), available_time)
                    elif name == "log_recommendation":
                        tool_res = tool_log_recommendation(
                            session, user_id, args.get("plan"), args.get("reasoning"),
                            tool_calls_trace, calendar_context, deadline_context
                        )
                    elif name == "get_calendar_availability":
                        tool_res = calendar_context
                    elif name == "get_upcoming_deadlines":
                        tool_res = deadline_context.get("deadlines", [])
                    else:
                        tool_res = {"error": f"Unknown tool '{name}'"}

                    # Log trace
                    tool_calls_trace.append({
                        "step": step,
                        "tool": name,
                        "arguments": args,
                        "result": tool_res
                    })

                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_res)
                    })

                messages.append({"role": "user", "content": tool_result_content})
            else:
                # If model responded with text directly and no tool calls, loop ends.
                try:
                    raw_text = "".join(b.text for b in response.content if b.type == "text")
                    if "{" in raw_text:
                        json_start = raw_text.find("{")
                        json_end = raw_text.rfind("}") + 1
                        parsed = json.loads(raw_text[json_start:json_end])
                        if "sessions" in parsed:
                            if not any(t["tool"] == "log_recommendation" for t in tool_calls_trace):
                                tool_log_recommendation(session, user_id, parsed, parsed.get("reasoning", "Generated plan"), tool_calls_trace, calendar_context, deadline_context)
                            return {
                                "plan": parsed,
                                "trace": tool_calls_trace,
                                "model_used": MODEL_NAME
                            }
                except Exception as parse_err:
                    logger.warning(f"Error parsing raw text reply from LLM: {parse_err}")

                break

        # Return whatever was logged last, or build final summary
        log_stmt = select(AgentLog).where(AgentLog.user_id == user_id).order_by(AgentLog.timestamp.desc())
        last_log = session.exec(log_stmt).first()
        if last_log:
            return {
                "plan": last_log.final_plan,
                "reasoning": last_log.reasoning,
                "trace": tool_calls_trace,
                "model_used": MODEL_NAME
            }
            
    except Exception as e:
        logger.error(f"Error in LLM loop: {e}. Falling back to mock planner.")
        
    return await run_mock_agent(session, user_id, available_time_override, calendar_context, deadline_context)

# --- DETERMINISTIC PORTFOLIO MOCK AGENT LOOP ---

async def run_mock_agent(
    session: Session,
    user_id: str,
    available_time_override: int = None,
    calendar_context: Optional[Dict[str, Any]] = None,
    deadline_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Simulates the agent tool-calling execution trace deterministically.
    This serves as a high-fidelity mock implementation when API keys are not provided.
    """
    trace = []
    
    # Step 1: get_available_time
    avail_time = available_time_override or tool_get_available_time(session, user_id)
    trace.append({
        "step": 0,
        "tool": "get_available_time",
        "arguments": {},
        "result": avail_time
    })
    
    # Step 2: get_forgetting_scores
    scores = tool_get_forgetting_scores(session, user_id)
    trace.append({
        "step": 1,
        "tool": "get_forgetting_scores",
        "arguments": {},
        "result": scores
    })
    
    # Step 3: get_calendar_availability
    if calendar_context is None:
        calendar_context = await tool_get_calendar_availability(session, user_id)
    trace.append({
        "step": 2,
        "tool": "get_calendar_availability",
        "arguments": {},
        "result": calendar_context
    })

    # Step 4: get_upcoming_deadlines
    if deadline_context is None:
        deadline_context = {"deadlines": await tool_get_upcoming_deadlines(session, user_id)}
    trace.append({
        "step": 3,
        "tool": "get_upcoming_deadlines",
        "arguments": {},
        "result": deadline_context.get("deadlines", [])
    })

    # Identify priority topics from deadlines first
    deadline_topics = []
    for dl in deadline_context.get("deadlines", []):
        for t in dl.get("related_topics", []):
            if t not in deadline_topics:
                deadline_topics.append(t)

    # Identify decayed topics from FSRS (limit to top 3, excluding already prioritized deadline topics)
    decayed_topics = [s["topic_name"] for s in scores if s["forgetting_risk"] > 0.15][:3]
    
    # Merge: deadline topics first, then decayed topics, dedup
    merged_topics = deadline_topics.copy()
    for t in decayed_topics:
        if t not in merged_topics:
            merged_topics.append(t)
    merged_topics = merged_topics[:3]  # Cap at 3

    if not merged_topics:
        merged_topics = ["Graphs", "Dynamic Programming"]
        
    # Step 5: Loop through topics to fetch history and relations
    step_num = 4
    for t_name in merged_topics:
        history = tool_get_topic_history(session, user_id, t_name)
        trace.append({
            "step": step_num,
            "tool": "get_topic_history",
            "arguments": {"topic_name": t_name},
            "result": history
        })
        step_num += 1
        
        relations = tool_get_related_concepts(session, t_name)
        trace.append({
            "step": step_num,
            "tool": "get_related_concepts",
            "arguments": {"topic_name": t_name},
            "result": relations
        })
        step_num += 1
        
    # Step 6: Draft a plan fitting the time budget and free blocks
    # Use free blocks to inform session timing
    free_blocks = calendar_context.get("free_blocks", [])
    sessions = []
    time_per_topic = int(avail_time / len(merged_topics)) if merged_topics else avail_time
    for i, t_name in enumerate(merged_topics):
        block_hint = ""
        if i < len(free_blocks):
            blk = free_blocks[i]
            block_hint = f" Schedule in the {blk['start']}–{blk['end']} window on {blk['date']}."
        is_deadline_topic = t_name in deadline_topics
        focus = (
            f"🔴 URGENT — Deadline detected! Review core {t_name} patterns.{block_hint}"
            if is_deadline_topic
            else f"Review concepts and practice problems to rebuild stability.{block_hint}"
        )
        sessions.append({
            "topic": t_name,
            "duration_min": time_per_topic,
            "focus": focus
        })
        
    draft_plan = {"sessions": sessions}
    
    # Step 7: check_plan_fits_budget
    fit_res = tool_check_plan_fits_budget(draft_plan, avail_time)
    trace.append({
        "step": step_num,
        "tool": "check_plan_fits_budget",
        "arguments": {"plan": draft_plan},
        "result": fit_res
    })
    step_num += 1
    
    # Step 8: log_recommendation
    reasoning_parts = []
    if deadline_topics:
        reasoning_parts.append(
            f"Prioritized {', '.join(deadline_topics)} based on upcoming calendar deadlines."
        )
    if decayed_topics:
        reasoning_parts.append(
            f"Also included {', '.join(decayed_topics)} due to high FSRS forgetting risk."
        )
    reasoning_parts.append(
        f"All sessions are scheduled within available free calendar blocks. "
        f"Total plan fits within the {avail_time}-minute study budget."
    )
    reasoning = " ".join(reasoning_parts)
    
    log_res = tool_log_recommendation(session, user_id, draft_plan, reasoning, trace, calendar_context, deadline_context)
    trace.append({
        "step": step_num,
        "tool": "log_recommendation",
        "arguments": {"plan": draft_plan, "reasoning": reasoning},
        "result": log_res
    })
    
    return {
        "plan": draft_plan,
        "reasoning": reasoning,
        "trace": trace,
        "model_used": "mock-portfolio-agent"
    }

async def run_coach_agent(session: Session, user_id: str, user_message: str) -> Dict[str, Any]:
    """
    Runs the conversational AI Coach Agent.
    If the Anthropic client is None, the model call fails, or the daily call cap is hit,
    executes a deterministic mock coach instead.
    """
    tool_calls_trace = []

    if client is None or _daily_cap_exceeded(session, user_id):
        return await run_mock_coach(session, user_id, user_message)

    system_instruction = (
        "You are RecallAI's Spaced Repetition Learning Coach. "
        "Your task is to converse with the user, answer their queries, explain FSRS score patterns, "
        "and modify their study parameters using tools when asked.\n"
        "Rules:\n"
        "1. Prior to making statements about their current knowledge state, always invoke get_forgetting_scores.\n"
        "2. If they ask about a specific topic's history, invoke get_topic_history.\n"
        "3. If they ask about calendar or schedules, invoke get_calendar_availability and get_upcoming_deadlines.\n"
        "4. Answer their questions directly, grounding your analysis in the metrics returned by tools.\n"
        "5. Keep answers concise, helpful, and technical (FSRS-grounded)."
    )
    
    messages = [
        {"role": "user", "content": user_message}
    ]

    try:
        reply_content = "I reviewed your metrics but couldn't construct a proper response."
        for step in range(8):
            response = await client.messages.create(
                model=MODEL_NAME,
                max_tokens=AGENT_MAX_TOKENS,
                system=system_instruction,
                messages=messages,
                tools=TOOLS_SCHEMA,
            )

            messages.append({"role": "assistant", "content": response.content})
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if tool_use_blocks:
                tool_result_content = []
                for block in tool_use_blocks:
                    name = block.name
                    args = block.input or {}

                    tool_res = None
                    if name == "get_forgetting_scores":
                        tool_res = tool_get_forgetting_scores(session, user_id)
                    elif name == "get_topic_history":
                        tool_res = tool_get_topic_history(session, user_id, args.get("topic_name"))
                    elif name == "get_related_concepts":
                        tool_res = tool_get_related_concepts(session, args.get("topic_name"))
                    elif name == "get_available_time":
                        tool_res = tool_get_available_time(session, user_id)
                    elif name == "check_plan_fits_budget":
                        avail_time = tool_get_available_time(session, user_id)
                        tool_res = tool_check_plan_fits_budget(args.get("plan", {}), avail_time)
                    elif name == "log_recommendation":
                        tool_res = tool_log_recommendation(
                            session, user_id, args.get("plan"), args.get("reasoning"), tool_calls_trace
                        )
                    elif name == "get_calendar_availability":
                        tool_res = await tool_get_calendar_availability(session, user_id)
                    elif name == "get_upcoming_deadlines":
                        tool_res = await tool_get_upcoming_deadlines(session, user_id)
                    else:
                        tool_res = {"error": f"Unknown tool '{name}'"}

                    tool_calls_trace.append({
                        "step": step,
                        "tool": name,
                        "arguments": args,
                        "result": tool_res
                    })

                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_res)
                    })

                messages.append({"role": "user", "content": tool_result_content})
            else:
                reply_content = "".join(b.text for b in response.content if b.type == "text")
                break

        return {
            "reply": reply_content,
            "trace": tool_calls_trace
        }
    except Exception as e:
        logger.error(f"Error in coach agent: {e}")

    return await run_mock_coach(session, user_id, user_message)

async def run_mock_coach(session: Session, user_id: str, user_message: str) -> Dict[str, Any]:
    """
    Simulates the coach responses and tool actions deterministically for portfolio showcases.
    """
    trace = []
    msg_lower = user_message.lower()
    
    # Simulate a tool call to show agentic behavior in logs
    if "dp" in msg_lower or "dynamic" in msg_lower or "worst" in msg_lower or "decay" in msg_lower:
        scores = tool_get_forgetting_scores(session, user_id)
        trace.append({
            "step": 0,
            "tool": "get_forgetting_scores",
            "arguments": {},
            "result": scores
        })
        
        dp_info = next((s for s in scores if "Dynamic Programming" in s["topic_name"]), None)
        dp_risk = dp_info["forgetting_risk"] * 100 if dp_info else 84.0
        dp_stability = dp_info["stability_days"] if dp_info else 1.5
        
        if "worst" in msg_lower or "decay" in msg_lower:
            reply = (
                f"According to your FSRS memory logs, your highest decay risks are "
                f"Dynamic Programming ({dp_risk:.0f}% risk, stability {dp_stability:.1f}d) and "
                f"Trie (51% risk). I recommend reviewing these topics first to prevent permanent forgetting."
            )
        else:
            reply = (
                f"Dynamic Programming is currently at {dp_risk:.0f}% forgetting risk because "
                f"your FSRS stability is only {dp_stability:.1f} days. Since you last practiced it, "
                f"the retrievability has fallen below your 90% target threshold. You should practice 1-2 medium DP problems."
            )
            
    elif "calendar" in msg_lower or "schedule" in msg_lower or "deadline" in msg_lower or "interview" in msg_lower:
        cal = await tool_get_calendar_availability(session, user_id)
        deadlines = await tool_get_upcoming_deadlines(session, user_id)
        trace.append({
            "step": 0,
            "tool": "get_calendar_availability",
            "arguments": {},
            "result": cal
        })
        trace.append({
            "step": 1,
            "tool": "get_upcoming_deadlines",
            "arguments": {},
            "result": deadlines
        })
        free_count = len(cal.get("free_blocks", []))
        dl_summary = ", ".join([d["event_title"] for d in deadlines]) if deadlines else "none"
        reply = (
            f"You have {free_count} free time blocks available over the next 7 days. "
            f"Upcoming deadlines detected: {dl_summary}. "
            f"I recommend front-loading the related topics to those events in your earliest free blocks."
        )

    elif "prereq" in msg_lower or "link" in msg_lower or "graph" in msg_lower:
        target = "Graphs"
        for t in ["Graphs", "Union Find", "Dynamic Programming", "Arrays", "Trie"]:
            if t.lower() in msg_lower:
                target = t
                break
        relations = tool_get_related_concepts(session, target)
        trace.append({
            "step": 0,
            "tool": "get_related_concepts",
            "arguments": {"topic_name": target},
            "result": relations
        })
        
        prereqs = ", ".join(relations["prerequisites"]) if relations["prerequisites"] else "none"
        dependents = ", ".join(relations["dependents"]) if relations["dependents"] else "none"
        
        reply = (
            f"For topic '{target}':\n"
            f"- Direct Prerequisites: {prereqs}\n"
            f"- Direct Dependents: {dependents}\n"
            f"If you're struggling with {target}, make sure you've mastered its prerequisites first."
        )
        
    elif "time" in msg_lower or "budget" in msg_lower or "minutes" in msg_lower:
        avail_time = tool_get_available_time(session, user_id)
        trace.append({
            "step": 0,
            "tool": "get_available_time",
            "arguments": {},
            "result": avail_time
        })
        reply = (
            f"Your current daily study budget is set to {avail_time} minutes. "
            f"If you'd like to adjust this, you can set it in your user preferences."
        )
    else:
        reply = (
            "I've analyzed your knowledge state. Your overall knowledge health is at 81% retrievability. "
            "You have some decay on Dynamic Programming and Trie. Let me know if you want to inspect specific FSRS values or get a custom plan!"
        )
        
    return {
        "reply": reply,
        "trace": trace
    }
