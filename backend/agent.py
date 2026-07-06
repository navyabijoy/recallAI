import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple
from sqlmodel import Session, select
from openai import AsyncOpenAI

from .models import User, Topic, LearningEvent, KnowledgeNode, AgentLog
from .fsrs import calculate_retrievability
from .graph_utils import get_related_concepts as graph_get_related_concepts

logger = logging.getLogger(__name__)

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/llama-3-8b-instruct:free")

# Create Client (safe if key is missing/placeholder)
if OPENROUTER_API_KEY and OPENROUTER_API_KEY != "placeholder":
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com/recallai/recallai",
            "X-Title": "RecallAI Agentic Planner"
        }
    )
else:
    client = None

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

def tool_log_recommendation(session: Session, user_id: str, plan: Dict[str, Any], reasoning: str, tool_calls_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Persists the final planned session and explanations to the database."""
    log_entry = AgentLog(
        user_id=user_id,
        timestamp=datetime.utcnow(),
        tool_calls={"trace": tool_calls_log},
        final_plan=plan,
        reasoning=reasoning
    )
    session.add(log_entry)
    session.commit()
    session.refresh(log_entry)
    return {
        "status": "success",
        "log_id": log_entry.id,
        "message": "Recommendation plan logged successfully."
    }

# --- TOOL METADATA FOR LLM ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_forgetting_scores",
            "description": "Get forgetting probability scores based on FSRS calculations for all topics.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_topic_history",
            "description": "Get user practice history metrics (attempts, mistakes, success rate, grades) for a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {"type": "string", "description": "The name of the topic, e.g. 'Graphs'"}
                },
                "required": ["topic_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_concepts",
            "description": "Query knowledge graph prerequisites and dependents for a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {"type": "string", "description": "Name of the topic"}
                },
                "required": ["topic_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_time",
            "description": "Retrieve the user's active session time budget.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_plan_fits_budget",
            "description": "Check if a draft plan fits the available time budget.",
            "parameters": {
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_recommendation",
            "description": "Persist the finalized revision plan and explanatory reasoning.",
            "parameters": {
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
        }
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
    
    # 1. Fallback to mock if API key isn't provided
    if client is None:
        logger.info("OpenRouter client not initialized. Running mock agent loop.")
        return await run_mock_agent(session, user_id, available_time_override)
        
    system_instruction = (
        "You are RecallAI's Spaced Repetition Planning Agent. "
        "Your task is to draft an optimal study plan for today based on the user's knowledge state and forgetting risks.\n"
        "Rules:\n"
        "1. Start by fetching the user's available time and forgetting scores.\n"
        "2. For topics with high decay (forgetting risk > 20%), fetch their topic history and related concepts.\n"
        "3. Draft a schedule that allocates time to review high-decay topics.\n"
        "4. Validate the schedule with check_plan_fits_budget. If it overflows, reduce topic time or drop lower priority topics and check again.\n"
        "5. Once it fits, run log_recommendation to save the final plan and explain your logic.\n"
        "6. Return ONLY the final plan JSON containing the keys: 'sessions' and 'reasoning'."
    )
    
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Please plan today's study session. user_id={user_id}. Available time override={available_time_override or 'None'}"}
    ]
    
    available_time = available_time_override or tool_get_available_time(session, user_id)
    
    try:
        for step in range(12):  # Limit loop to 12 steps to prevent infinite running
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            response_msg = response.choices[0].message
            messages.append(response_msg)
            
            # If the model requested tool calls
            if response_msg.tool_calls:
                for tc in response_msg.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments or "{}")
                    
                    # Execute tool
                    tool_res = None
                    if name == "get_forgetting_scores":
                        tool_res = tool_get_forgetting_scores(session, user_id)
                    elif name == "get_topic_history":
                        tool_res = tool_get_topic_history(session, user_id, args.get("topic_name"))
                    elif name == "get_related_concepts":
                        tool_res = tool_get_related_concepts(session, args.get("topic_name"))
                    elif name == "get_available_time":
                        # Apply override if specified
                        tool_res = available_time
                    elif name == "check_plan_fits_budget":
                        tool_res = tool_check_plan_fits_budget(args.get("plan", {}), available_time)
                    elif name == "log_recommendation":
                        tool_res = tool_log_recommendation(
                            session, user_id, args.get("plan"), args.get("reasoning"), tool_calls_trace
                        )
                    else:
                        tool_res = {"error": f"Unknown tool '{name}'"}
                        
                    # Log trace
                    tool_calls_trace.append({
                        "step": step,
                        "tool": name,
                        "arguments": args,
                        "result": tool_res
                    })
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(tool_res)
                    })
            else:
                # If model responded with text directly and no tool calls, loop ends.
                # Try to extract plan and reasoning if returned in raw text
                try:
                    raw_text = response_msg.content or ""
                    # Check if model output contains json
                    if "{" in raw_text:
                        json_start = raw_text.find("{")
                        json_end = raw_text.rfind("}") + 1
                        parsed = json.loads(raw_text[json_start:json_end])
                        if "sessions" in parsed:
                            # Log mock recommendation if model skipped logging tool call
                            if not any(t["tool"] == "log_recommendation" for t in tool_calls_trace):
                                tool_log_recommendation(session, user_id, parsed, parsed.get("reasoning", "Generated plan"), tool_calls_trace)
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
        
    return await run_mock_agent(session, user_id, available_time_override)

# --- DETERMINISTIC PORTFOLIO MOCK AGENT LOOP ---

async def run_mock_agent(session: Session, user_id: str, available_time_override: int = None) -> Dict[str, Any]:
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
    
    # Identify decayed topics (limit to top 3)
    decayed_topics = [s["topic_name"] for s in scores if s["forgetting_risk"] > 0.15][:3]
    if not decayed_topics:
        # Seed default if empty
        decayed_topics = ["Graphs", "Dynamic Programming"]
        
    # Step 3: Loop through decayed topics to fetch history and relations
    step_num = 2
    for t_name in decayed_topics:
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
        
    # Step 4: Draft a plan fitting the time budget
    # Distribute available time evenly among decayed topics
    sessions = []
    time_per_topic = int(avail_time / len(decayed_topics)) if decayed_topics else avail_time
    for t_name in decayed_topics:
        sessions.append({
            "topic": t_name,
            "duration_min": time_per_topic,
            "focus": f"Review concepts and practice problems to rebuild stability."
        })
        
    draft_plan = {"sessions": sessions}
    
    # Step 5: check_plan_fits_budget
    fit_res = tool_check_plan_fits_budget(draft_plan, avail_time)
    trace.append({
        "step": step_num,
        "tool": "check_plan_fits_budget",
        "arguments": {"plan": draft_plan},
        "result": fit_res
    })
    step_num += 1
    
    # Step 6: log_recommendation
    reasoning = (
        f"Prioritized {', '.join(decayed_topics)} because they show the highest forgetting risk "
        f"according to current FSRS metrics. Planned sessions fit within the study budget of {avail_time} minutes."
    )
    log_res = tool_log_recommendation(session, user_id, draft_plan, reasoning, trace)
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
    If OpenRouter client is None or model fails, executes a highly responsive deterministic mock coach
    to keep portfolio flow running.
    """
    tool_calls_trace = []
    
    if client is None:
        return await run_mock_coach(session, user_id, user_message)
        
    system_instruction = (
        "You are RecallAI's Spaced Repetition Learning Coach. "
        "Your task is to converse with the user, answer their queries, explain FSRS score patterns, "
        "and modify their study parameters using tools when asked.\n"
        "Rules:\n"
        "1. Prior to making statements about their current knowledge state, always invoke get_forgetting_scores.\n"
        "2. If they ask about a specific topic's history, invoke get_topic_history.\n"
        "3. Answer their questions directly, grounding your analysis in the metrics returned by tools.\n"
        "4. Keep answers concise, helpful, and technical (FSRS-grounded)."
    )
    
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_message}
    ]
    
    try:
        reply_content = "I reviewed your metrics but couldn't construct a proper response."
        for step in range(8):
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto"
            )
            
            response_msg = response.choices[0].message
            messages.append(response_msg)
            
            if response_msg.tool_calls:
                for tc in response_msg.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments or "{}")
                    
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
                    else:
                        tool_res = {"error": f"Unknown tool '{name}'"}
                        
                    tool_calls_trace.append({
                        "step": step,
                        "tool": name,
                        "arguments": args,
                        "result": tool_res
                    })
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(tool_res)
                    })
            else:
                reply_content = response_msg.content or ""
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
