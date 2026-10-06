"""
agents/graph/state.py
─────────────────────
LangGraph AgentState schema for the DataOps AI multi-turn conversational agent.
Complies with Phase P11.1.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    State schema for the LangGraph multi-turn conversational agent graph.
    """
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    user_role: str
    department_id: str | None
    session_id: str
    query_id: str | None
    turn_id: str
    event_job_id: str | None           # set only for event turns (P11.10)
    rag_status: dict
    rag_hits: list
    slots: dict                        # category, city, us_state, quantity, required_fields, source, fresh_within_days
    last_search: dict | None           # turn_id, slots_hash, total, returned, lead_ids, sufficient, reasons
    pending_proposal: dict | None      # id, source, args, missing, question, tool_call_id
    confirmed: bool
    active_job_id: str | None
    decision: str | None               # D10: DB | KB | SCRAPER | PARTIAL | CLARIFY | NONE | DECLINED
    summary: str
    tool_steps: int
    trace: list                        # ordered tool trace for this turn
    degraded: bool
