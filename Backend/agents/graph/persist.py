"""
agents/graph/persist.py
───────────────────────
State persistence and database synchronization for LangGraph agent turns.
Complies with Phase P11.8 and Decision D17 (deterministic IDs).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from Database.controller import session_scope
from Database.models.message import AgentMessage
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.session import AgentSession
from agents.graph.state import AgentState

logger = logging.getLogger(__name__)


def _compute_decision(state: AgentState) -> str:
    """Compute the decision code when no scrape job was triggered."""
    if state.get("decision"):
        return state["decision"]

    last_search = state.get("last_search") or {}
    rag_hits = state.get("rag_hits") or []
    trace = state.get("trace") or []

    if last_search.get("sufficient"):
        return "DB"
    if rag_hits and not last_search.get("returned"):
        return "KB"
    if not trace:
        return "NONE"
    return "CLARIFY"


def save_turn(state: AgentState, client_message_id: Optional[str] = None) -> None:
    """
    Persist completed conversational turn into queries, query_results,
    and agent_messages within a single scoped session.
    """
    session_id = state.get("session_id")
    if not session_id:
        return

    query_id = state.get("query_id")
    turn_id = state.get("turn_id", "")
    cid = client_message_id or turn_id or "turn"

    # Extract user message and assistant reply from messages
    messages = state.get("messages", [])
    user_text = ""
    reply_text = ""

    for msg in messages:
        if getattr(msg, "type", None) == "human":
            user_text = str(msg.content)
        elif getattr(msg, "type", None) == "ai" and not getattr(msg, "tool_calls", None):
            reply_text = str(msg.content)

    user_msg_id = f"msg-{cid}-user"
    asst_msg_id = f"msg-{cid}-assistant"

    decision = _compute_decision(state)
    last_search = state.get("last_search") or {}
    lead_ids = last_search.get("lead_ids") or []
    active_job_id = state.get("active_job_id")

    try:
        with session_scope() as session:
            # 1. Ensure AgentSession exists
            sess = session.get(AgentSession, session_id)
            if not sess:
                sess = AgentSession(
                    id=session_id,
                    user_id=state.get("user_id"),
                    department_id=state.get("department_id") or "dept-default",
                    agent_id="agent-master",
                    title=user_text[:50] if user_text else "Conversation",
                    status="active",
                )
                session.add(sess)
                session.flush()

            # 2. Persist user message (deterministic ID, check existing)
            if user_text:
                existing_user_msg = session.get(AgentMessage, user_msg_id)
                if not existing_user_msg:
                    session.add(
                        AgentMessage(
                            id=user_msg_id,
                            session_id=session_id,
                            sender="user",
                            role="user",
                            text=user_text,
                            message_metadata={"query_id": query_id, "turn_id": turn_id},
                        )
                    )

            # 3. Persist assistant reply (deterministic ID)
            if reply_text:
                existing_asst_msg = session.get(AgentMessage, asst_msg_id)
                if not existing_asst_msg:
                    session.add(
                        AgentMessage(
                            id=asst_msg_id,
                            session_id=session_id,
                            sender="agent",
                            role="agent",
                            text=reply_text,
                            message_metadata={
                                "query_id": query_id,
                                "turn_id": turn_id,
                                "jobId": active_job_id,
                                "decision": decision,
                            },
                            tool_trace={"trace": state.get("trace", [])},
                        )
                    )

            # 4. Update Query record
            if query_id:
                q = session.get(Query, query_id)
                if q:
                    rag_status = state.get("rag_status") or {}
                    rag_hits = state.get("rag_hits") or []
                    q.parameters = {
                        "slots": state.get("slots", {}),
                        "rag_state": rag_status.get("state"),
                        "rag_hit_ids": [h.get("chunkId") for h in rag_hits if isinstance(h, dict)],
                    }
                    q.decision = decision
                    q.status = "completed"
                    q.served_at = datetime.now(timezone.utc)
                    q.job_id = active_job_id
                    q.records_returned = len(lead_ids)

                    # 5. Write query_results for returned leads (rank order)
                    for rank, lid in enumerate(lead_ids):
                        existing_qr = session.get(QueryResult, (query_id, lid))
                        if not existing_qr:
                            session.add(QueryResult(query_id=query_id, lead_id=lid, rank=rank))

            # 6. Mark any pending system events for this session as notified
            event_msgs = session.scalars(
                select(AgentMessage)
                .where(AgentMessage.session_id == session_id)
                .where(AgentMessage.role == "system_event")
            ).all()
            for em in event_msgs:
                meta = dict(em.message_metadata or {})
                if not meta.get("notified"):
                    meta["notified"] = True
                    em.message_metadata = meta

    except Exception as e:
        logger.error("persist.save_turn error: %s", e, exc_info=True)


def save_paused_turn(
    state: AgentState,
    client_message_id: Optional[str] = None,
) -> None:
    """
    Persist turn interrupted for user confirmation.
    Stores confirmation question as assistant display message.
    """
    session_id = state.get("session_id")
    if not session_id:
        return

    query_id = state.get("query_id")
    turn_id = state.get("turn_id", "")
    cid = client_message_id or turn_id or "turn"

    proposal = state.get("pending_proposal") or {}
    question_text = proposal.get("question") or "Would you like me to run this scrape?"

    user_msg_id = f"msg-{cid}-user"
    asst_msg_id = f"msg-{cid}-assistant"

    messages = state.get("messages", [])
    user_text = ""
    for msg in messages:
        if getattr(msg, "type", None) == "human":
            user_text = str(msg.content)

    try:
        with session_scope() as session:
            # User message
            if user_text:
                if not session.get(AgentMessage, user_msg_id):
                    session.add(
                        AgentMessage(
                            id=user_msg_id,
                            session_id=session_id,
                            sender="user",
                            role="user",
                            text=user_text,
                            message_metadata={"query_id": query_id, "turn_id": turn_id},
                        )
                    )

            # Assistant confirmation question
            if not session.get(AgentMessage, asst_msg_id):
                session.add(
                    AgentMessage(
                        id=asst_msg_id,
                        session_id=session_id,
                        sender="agent",
                        role="assistant",
                        text=question_text,
                        message_metadata={
                            "kind": "confirmation_question",
                            "proposal": proposal,
                            "query_id": query_id,
                            "turn_id": turn_id,
                        },
                    )
                )

            # Update Query status
            if query_id:
                q = session.get(Query, query_id)
                if q:
                    q.status = "awaiting_confirmation"
                    q.parameters = {"slots": state.get("slots", {})}

    except Exception as e:
        logger.error("persist.save_paused_turn error: %s", e, exc_info=True)


def save_llm_failure(
    session_id: str,
    query_id: Optional[str],
    text: str,
    client_message_id: Optional[str] = None,
) -> None:
    """Persist turn when LLM is unavailable (503 / D4)."""
    cid = client_message_id or "failure"
    user_msg_id = f"msg-{cid}-user"

    try:
        with session_scope() as session:
            if not session.get(AgentMessage, user_msg_id):
                session.add(
                    AgentMessage(
                        id=user_msg_id,
                        session_id=session_id,
                        sender="user",
                        role="user",
                        text=text,
                    )
                )

            if query_id:
                q = session.get(Query, query_id)
                if q:
                    q.status = "llm_unavailable"
                    q.decision = "LLM_UNAVAILABLE"
    except Exception as e:
        logger.error("persist.save_llm_failure error: %s", e, exc_info=True)


def save_event_turn(
    session_id: str,
    job_id: str,
    query_id: Optional[str],
    reply_text: str,
) -> None:
    """Persist notification message for an asynchronous job event turn."""
    asst_msg_id = f"msg-evt-{job_id}-assistant"

    try:
        with session_scope() as session:
            if not session.get(AgentMessage, asst_msg_id):
                session.add(
                    AgentMessage(
                        id=asst_msg_id,
                        session_id=session_id,
                        sender="agent",
                        role="assistant",
                        text=reply_text,
                        message_metadata={
                            "job_id": job_id,
                            "query_id": query_id,
                            "event": True,
                        },
                    )
                )

            if query_id:
                q = session.get(Query, query_id)
                if q:
                    q.job_id = job_id
    except Exception as e:
        logger.error("persist.save_event_turn error: %s", e, exc_info=True)
