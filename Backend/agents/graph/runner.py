"""
agents/graph/runner.py
──────────────────────
API integration points for the LangGraph v2 agent.
Provides run_turn(), which handles interrupts, resumption, and response formatting.
"""

import json
import logging
import threading
from typing import Any, Dict

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agents.graph.graph import get_compiled_graph
from Database.models.user import User

logger = logging.getLogger(__name__)

# Simple in-memory lock per session to serialize concurrent requests to the same thread
_session_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

def _get_lock(session_id: str) -> threading.Lock:
    with _locks_lock:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]

def pending_interrupt(graph, config):
    """Check if the graph is currently interrupted awaiting user input."""
    state = graph.get_state(config)
    return state.tasks and any(t.interrupts for t in state.tasks)


def classify_confirmation(text: str, pending: Any) -> dict:
    """
    Very simple classification.
    Real implementation might use a small LLM call to classify
    "yes", "no", "change it to 50".
    For now, fallback to exact matching or simple keywords.
    """
    t = text.lower().strip()
    if t in ["yes", "y", "haan", "go ahead", "approve", "ok", "sure", "do it"]:
        return {"decision": "approve", "text": text}
    if t in ["no", "n", "cancel", "stop", "reject"]:
        return {"decision": "reject", "text": text}
    # Otherwise treat as an unrelated question or modification
    if "only" in t or "change" in t:
        return {"decision": "modify", "edits": text, "text": text}
    return {"decision": "unrelated", "text": text}


def to_api_response(out: dict, state_snapshot) -> dict:
    """Format LangGraph state into the existing API contract."""
    state = state_snapshot.values
    messages = state.get("messages", [])
    
    # Extract the last AI message
    last_ai_msg = ""
    for msg in reversed(messages):
        if msg.type == "ai" and msg.content:
            last_ai_msg = msg.content
            break

    slots = state.get("slots", {})
    req = {
        "industry": slots.get("category", "Not specified"),
        "location": slots.get("city") or slots.get("location", "Not specified"),
        "companySize": "Not specified",
        "decisionMakers": [],
        "quantity": slots.get("limit", 20),
        "completionPercentage": 10,
        "status": "collecting",
    }

    # If currently interrupted, we format a special response
    if state_snapshot.tasks and any(t.interrupts for t in state_snapshot.tasks):
        interrupts = [i.value for t in state_snapshot.tasks for i in t.interrupts]
        interrupt_val = interrupts[-1] if interrupts else None
        return {
            "reply": last_ai_msg or "I have a proposal for you.",
            "updatedRequirement": req,
            "suggestions": [],
            "pendingAction": interrupt_val,
            "sessionId": state.get("session_id"),
        }

    return {
        "reply": last_ai_msg or "No response generated.",
        "updatedRequirement": req,
        "suggestions": [],
        "degraded": state.get("degraded", False),
        "jobId": state.get("job_id"),
        "sessionId": state.get("session_id"),
    }


def run_turn(user: User, session_id: str, text: str) -> dict:
    """
    Execute one turn of the agent conversation.
    """
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 25}
    
    with _get_lock(session_id):
        pending = pending_interrupt(graph, config)
        if pending:
            decision = classify_confirmation(text, pending)
            out = graph.invoke(Command(resume=decision), config)
        else:
            out = graph.invoke({
                "messages": [HumanMessage(content=text)],
                "user_id": user.id,
                "session_id": session_id,
                "tool_steps": 0,
            }, config)
            
        return to_api_response(out, graph.get_state(config))
