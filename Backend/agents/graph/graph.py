"""
agents/graph/graph.py
─────────────────────
LangGraph StateGraph Builder — compiles the agent workflow into an executable graph.

Architecture:
    parse_input → classify_intent → [route] → handler → respond
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END

from agents.graph.state import AgentState
from agents.graph.nodes import (
    parse_input,
    classify_intent,
    handle_greeting,
    check_database,
    ask_scraper_permission,
    handle_scraper_request,
    handle_job_status,
    handle_dataset_query,
    respond,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional Router
# ---------------------------------------------------------------------------

def route_after_classify(state: AgentState) -> str:
    """Route to the correct handler node based on classified intent."""
    return state.get("route", "greeting")


def route_after_db_check(state: AgentState) -> str:
    """After checking the database, either respond (sufficient) or ask permission."""
    if state.get("db_sufficient", False):
        return "respond"
    return "ask_scraper_permission"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

def build_agent_graph() -> StateGraph:
    """
    Build and compile the LangGraph StateGraph for the agent orchestrator.

    Graph topology:
        parse_input
            ↓
        classify_intent
            ↓ (conditional)
        ┌──────────────────────────────────────────┐
        │ greeting         → respond               │
        │ check_database   → [sufficient?]          │
        │                    yes → respond          │
        │                    no  → ask_permission   │
        │                         → respond         │
        │ scraper_request  → respond               │
        │ job_status       → respond               │
        │ dataset_query    → respond               │
        └──────────────────────────────────────────┘
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────────────────────────
    graph.add_node("parse_input", parse_input)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("handle_greeting", handle_greeting)
    graph.add_node("check_database", check_database)
    graph.add_node("ask_scraper_permission", ask_scraper_permission)
    graph.add_node("handle_scraper_request", handle_scraper_request)
    graph.add_node("handle_job_status", handle_job_status)
    graph.add_node("handle_dataset_query", handle_dataset_query)
    graph.add_node("respond", respond)

    # ── Set entry point ───────────────────────────────────────────────────
    graph.set_entry_point("parse_input")

    # ── Linear edges ──────────────────────────────────────────────────────
    graph.add_edge("parse_input", "classify_intent")

    # ── Conditional routing after intent classification ────────────────────
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "greeting": "handle_greeting",
            "check_database": "check_database",
            "scraper_request": "handle_scraper_request",
            "job_status": "handle_job_status",
            "dataset_query": "handle_dataset_query",
        },
    )

    # ── Conditional routing after database check ──────────────────────────
    graph.add_conditional_edges(
        "check_database",
        route_after_db_check,
        {
            "respond": "respond",
            "ask_scraper_permission": "ask_scraper_permission",
        },
    )

    # ── Terminal edges → respond → END ────────────────────────────────────
    graph.add_edge("handle_greeting", "respond")
    graph.add_edge("ask_scraper_permission", "respond")
    graph.add_edge("handle_scraper_request", "respond")
    graph.add_edge("handle_job_status", "respond")
    graph.add_edge("handle_dataset_query", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Module-level compiled graph (singleton)
# ---------------------------------------------------------------------------

_compiled_graph = None


def get_compiled_graph():
    """Return the compiled LangGraph (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph()
        logger.info("LangGraph agent graph compiled successfully.")
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public API — run the graph
# ---------------------------------------------------------------------------

def run_agent_graph(
    session_id: str,
    message: str,
    current_requirement: Optional[Dict[str, Any]] = None,
    user_id: str = "usr-ahmed",
    department_id: str = "dept-sales-1",
) -> Dict[str, Any]:
    """
    Execute the full LangGraph agent pipeline.

    Returns the same dict shape as the old AgentOrchestrator.handle_message()
    for full backward compatibility with the frontend.
    """
    graph = get_compiled_graph()

    initial_state: AgentState = {
        "session_id": session_id,
        "message": message,
        "current_requirement": current_requirement,
        "user_id": user_id,
        "department_id": department_id,
    }

    try:
        final_state = graph.invoke(initial_state)

        # Build the response dict matching frontend BotChatResponse contract
        norm_query = final_state.get("norm_query")
        req_record = final_state.get("req_record")

        updated_requirement = _requirement_to_dict(req_record, norm_query) if req_record else (
            current_requirement or {
                "industry": "Not specified",
                "location": "Not specified",
                "companySize": "Not specified",
                "decisionMakers": [],
                "quantity": 0,
                "completionPercentage": 10,
                "status": "collecting",
            }
        )

        return {
            "reply": final_state.get("reply_text", "Something went wrong. Please try again."),
            "suggestions": final_state.get("suggestions", []),
            "updatedRequirement": updated_requirement,
            "recommendedScript": (req_record.selected_script if req_record else None),
            "sessionId": final_state.get("resolved_session_id", session_id),
            "decision": final_state.get("decision", "NEED_CLARIFICATION"),
            "query": norm_query.to_dict() if norm_query else None,
            "agentCode": final_state.get("agent_code", "orchestrator"),
            "handledBy": final_state.get("handled_by", "LangGraphOrchestrator"),
            "agentResult": final_state.get("agent_result"),
            "proposedActions": final_state.get("proposed_actions", []),
            "jobId": final_state.get("job_id"),
            "collaborationId": None,
            "collaborationStatus": None,
            "agentsInvolved": [final_state.get("agent_code", "orchestrator")],
            "agentSteps": [],
            "workflowStatus": final_state.get("workflow_status", "COMPLETED"),
            "intent": final_state.get("intent_dict"),
        }

    except Exception as exc:
        tb = traceback.format_exc()
        logger.error(f"LangGraph execution error: {exc}\n{tb}")
        print(f"[LangGraph] Error: {exc}\n{tb}")
        return _error_response(session_id, "An internal error occurred. Please try again.", current_requirement)


# ---------------------------------------------------------------------------
# Helpers (same logic as original orchestrator)
# ---------------------------------------------------------------------------

def _requirement_to_dict(req, query) -> Dict[str, Any]:
    """Serialize Requirement ORM object to frontend dict shape."""
    # When no specific fields are requested, default all to True (backwards-compatible).
    # When specific fields ARE requested, only those fields are marked True.
    req_fields = (query.requested_fields if query else []) or []
    all_fields = not req_fields  # True if no specific fields were requested
    field_flags = {
        "companyName": True,
        "contactName": True,
        "jobTitle": True,
        "email": all_fields or "email" in req_fields,
        "phone": all_fields or "phone" in req_fields,
        "website": all_fields or "website" in req_fields,
    }
    return {
        "id": req.id if req else "",
        "industry": (req.industry if req else None) or (query.category if query else None) or "Not specified",
        "location": (req.location if req else None) or (query.location if query else None) or "Not specified",
        "companySize": (req.company_size if req else None) or "Not specified",
        "companyType": getattr(query, "company_type", None) or "Not specified",
        "decisionMakers": (req.decision_makers if req else None) or [],
        "quantity": (req.quantity if req else None) or (query.quantity if query else None) or 20,
        "completionPercentage": req.completion_percentage if req else 10,
        "status": req.status if req else "collecting",
        "selectedScript": req.selected_script if req else None,
        "selectedScriptName": req.selected_script_name if req else None,
        "datasetId": getattr(req, "dataset_id", None),
        "requiredFields": field_flags,
    }


def _error_response(session_id: str, message: str, current_requirement: Optional[Dict]) -> Dict[str, Any]:
    """Fallback error response matching frontend contract."""
    req = current_requirement or {
        "industry": "Not specified",
        "location": "Not specified",
        "companySize": "Not specified",
        "decisionMakers": [],
        "quantity": 0,
        "completionPercentage": 10,
        "status": "collecting",
    }
    return {
        "reply": message,
        "suggestions": [],
        "updatedRequirement": req,
        "recommendedScript": None,
        "sessionId": session_id,
        "decision": "NEED_CLARIFICATION",
        "query": None,
        "agentCode": "orchestrator",
        "handledBy": "LangGraphOrchestrator",
        "agentResult": None,
        "proposedActions": [],
        "jobId": None,
        "collaborationId": None,
        "collaborationStatus": None,
        "agentsInvolved": [],
        "agentSteps": [],
        "workflowStatus": "FAILED",
    }
