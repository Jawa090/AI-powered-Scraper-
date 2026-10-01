"""
agents/graph/state.py
─────────────────────
LangGraph State Schema — typed dictionary that flows through every node.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    """
    Shared state that flows through the LangGraph StateGraph.
    Every node reads from and writes to this dictionary.
    """

    # ── Inputs (set once at graph entry) ──────────────────────────────────
    session_id: str
    message: str
    current_requirement: Optional[Dict[str, Any]]
    user_id: str
    department_id: str

    # ── Resolved during parse_input ───────────────────────────────────────
    resolved_session_id: str
    agent_session: Any            # AgentSession ORM object
    req_record: Any               # Requirement ORM object
    norm_query: Any               # NormalizedQuery
    data_availability: Any        # DataAvailabilityResult

    # ── Resolved during classify_intent ───────────────────────────────────
    intent: Any                   # StructuredIntent
    route: str                    # routing decision string

    # ── Resolved during check_database ────────────────────────────────────
    db_count: int
    db_sufficient: bool
    db_records: List[Dict[str, Any]]

    # ── Output (set by handler nodes, consumed by respond) ────────────────
    reply_text: str
    suggestions: List[str]
    decision: str
    proposed_actions: List[Dict[str, Any]]
    agent_code: str
    handled_by: str
    job_id: Optional[str]
    dataset_id: Optional[str]
    workflow_status: str
    agent_result: Optional[Dict[str, Any]]
    intent_dict: Optional[Dict[str, Any]]
