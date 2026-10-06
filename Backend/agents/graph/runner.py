"""
agents/graph/runner.py
──────────────────────
API integration and execution orchestrator for the LangGraph agent.
Complies with Phase P11.7, P11.9, P11.10 and Experiments E2, E3, E4, E7, E8, E11.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Literal, Optional

import psycopg
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy import select

from Database.controller import session_scope
from Database.models.message import AgentMessage
from Database.models.query import Query
from Database.models.session import AgentSession
from Database.models.user import User
from agents.graph.graph import get_compiled_graph
from agents.graph.persist import (
    save_event_turn,
    save_llm_failure,
    save_paused_turn,
    save_turn,
)
from agents.graph.state import AgentState
from agents.llm.chat_model import LLMUnavailable, get_chat_model, invoke_structured
from settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured Models for Confirmation
# ---------------------------------------------------------------------------

class ConfirmationDecision(BaseModel):
    decision: Literal["approve", "reject", "modify", "unrelated"] = Field(
        ...,
        description="Classification: approve, reject, modify, or unrelated.",
    )
    edits: Optional[str] = Field(
        default=None,
        description="If decision is modify, details of requested changes.",
    )
    text: str = Field(..., description="The user's original response text.")


# ---------------------------------------------------------------------------
# PostgreSQL Advisory Lock per Session (P11.7 Step 2)
# ---------------------------------------------------------------------------

@contextmanager
def session_lock(session_id: str, timeout_s: float = 30.0):
    """
    Dedicated PostgreSQL connection holding pg_try_advisory_lock(hashtextextended(:sid, 0)).
    Retries up to timeout_s; raises 409 'session busy' if timed out.
    """
    deadline = time.time() + timeout_s
    acquired = False
    conn = psycopg.connect(settings.CHECKPOINT_DB_URL, autocommit=True)
    try:
        while time.time() < deadline:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0));", (session_id,))
                row = cur.fetchone()
                if row and row[0]:
                    acquired = True
                    break
            time.sleep(0.1)

        if not acquired:
            raise HTTPException(status_code=409, detail="Session is busy with another active request.")

        yield
    finally:
        if acquired:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0));", (session_id,))
            except Exception as e:
                logger.warning("Error releasing session advisory lock: %s", e)
        conn.close()


def _get_lock(session_id: str):
    """Compatibility context manager adapter."""
    return session_lock(session_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pending_interrupt(graph, config: dict) -> bool:
    """Check if the graph is currently interrupted awaiting confirmation (E2)."""
    state = graph.get_state(config)
    return bool(state.interrupts)


def classify_confirmation(text: str, pending: Any) -> Dict[str, Any]:
    """
    Classify user confirmation using LLM structured output with heuristic fallback.
    """
    try:
        question = ""
        if isinstance(pending, dict):
            question = pending.get("question", "")

        prompt = (
            f"The user was asked: '{question}' regarding a proposed web scrape.\n"
            f"The user replied: '{text}'.\n"
            f"Classify their reply into one of: 'approve', 'reject', 'modify', or 'unrelated'."
        )
        res = invoke_structured(
            ConfirmationDecision,
            [HumanMessage(content=prompt)],
            max_retries=1,
        )
        if isinstance(res, ConfirmationDecision):
            return res.model_dump()
        elif isinstance(res, dict):
            return res
    except Exception as e:
        logger.warning("Confirmation classification via LLM failed, using heuristics: %s", e)

    # Deterministic heuristic fallback
    t = text.lower().strip()
    words = set(re.findall(r"\b\w+\b", t))
    approve_phrases = ["go ahead", "do it", "yes, run", "sure", "proceed"]
    reject_phrases = ["cancel this", "no, don't", "dont run"]
    modify_phrases = ["only", "change", "modify", "limit", "instead"]

    if any(p in t for p in modify_phrases) or any(w in words for w in ["change", "modify", "limit", "instead"]):
        return {"decision": "modify", "edits": text, "text": text}
    if any(p in t for p in reject_phrases) or any(w in words for w in ["no", "n", "cancel", "stop", "reject", "nah"]):
        return {"decision": "reject", "text": text}
    if any(p in t for p in approve_phrases) or any(w in words for w in ["yes", "y", "haan", "approve", "ok", "sure", "confirm", "proceed"]):
        return {"decision": "approve", "text": text}
    return {"decision": "unrelated", "text": text}


def to_api_response(
    out: Any,
    state_snapshot: Any,
    query_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format LangGraph state into the API response schema complying with Phase P11.9.
    """
    state = state_snapshot.values if hasattr(state_snapshot, "values") else (out or {})
    messages = state.get("messages", [])

    # Extract last assistant message
    last_ai_text = ""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "ai" and not getattr(msg, "tool_calls", None):
            last_ai_text = getattr(msg, "content", "")
            break

    slots = state.get("slots") or {}
    req = {
        "industry": slots.get("category"),
        "location": slots.get("city") or slots.get("us_state") or slots.get("location"),
        "companySize": None,
        "decisionMakers": [],
        "quantity": slots.get("quantity", 20),
        "completionPercentage": 10 if not state.get("active_job_id") else 50,
        "status": "collecting" if not state.get("active_job_id") else "scraping",
    }

    last_search = state.get("last_search") or {}
    items = []
    total = last_search.get("total", 0)

    # Lead records if available
    lead_ids = last_search.get("lead_ids", [])
    if lead_ids:
        try:
            from routes.serializers import serialize_lead
            from Database.controller import Repositories, session_scope

            with session_scope() as session:
                repo = Repositories(session).leads
                for lid in lead_ids[:20]:
                    lead = repo.get_by_id(lid)
                    if lead:
                        items.append(serialize_lead(lead))
        except Exception as e:
            logger.debug("Error serializing leads for API response: %s", e)

    rag_status = state.get("rag_status") or {}
    rag_hits = state.get("rag_hits") or []
    kb_info = {
        "state": rag_status.get("state", "not_configured"),
        "available": rag_status.get("available", False),
        "hits": [
            {
                "chunkId": h.get("chunkId"),
                "title": h.get("title"),
                "score": h.get("score"),
            }
            for h in rag_hits
            if isinstance(h, dict)
        ],
    }

    # Interrupted state (pending confirmation)
    pending_action = None
    proposed_actions = []

    if state_snapshot.interrupts:
        pending_action = state_snapshot.interrupts[0].value
        proposal = state.get("pending_proposal") or {}
        proposed_actions.append({
            "actionType": "scrape",
            "label": proposal.get("question") or "Would you like me to run this scrape?",
            "parameters": proposal.get("args") or {},
            "requiresConfirmation": True,
        })
        if not last_ai_text:
            last_ai_text = proposal.get("question") or "I have a scrape proposal ready for your confirmation."

    return {
        "reply": last_ai_text or "No response generated.",
        "records": items,
        "total": total,
        "queryId": query_id or state.get("query_id"),
        "decision": state.get("decision"),
        "jobId": state.get("active_job_id"),
        "updatedRequirement": req,
        "proposedActions": proposed_actions,
        "pendingAction": pending_action,
        "kb": kb_info,
        "suggestions": [],
        "sessionId": state.get("session_id"),
        "degraded": state.get("degraded", False),
    }


# ---------------------------------------------------------------------------
# Main Turn Execution: run_turn (P11.7)
# ---------------------------------------------------------------------------

def run_turn(
    user: Any,
    session_id: str,
    text: str,
    client_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute one turn of the multi-turn conversational agent graph.
    Handles locking, retries, interrupts, resumption, and D4/D9 compliance.
    """
    graph = get_compiled_graph()
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": getattr(settings, "RECURSION_LIMIT", 25),
    }

    user_id = getattr(user, "id", str(user))
    user_role = getattr(user, "role", "user")
    department_id = getattr(user, "department_id", None) or "dept-default"

    # Step 1: Ensure session exists & verify ownership (D9)
    with session_scope() as session:
        sess = session.get(AgentSession, session_id)
        if sess:
            if sess.user_id != user_id and user_role != "admin":
                raise HTTPException(status_code=403, detail="Session does not belong to you.")
        else:
            sess = AgentSession(
                id=session_id,
                user_id=user_id,
                department_id=department_id,
                agent_id="agent-master",
                title=text[:50] if text else "New Session",
                status="active",
            )
            session.add(sess)
            session.commit()

    # Step 2: Acquire session lock
    with session_lock(session_id):
        # Step 3: Check for retry of same message
        if client_message_id:
            with session_scope() as session:
                existing_q = session.scalar(
                    select(Query)
                    .where(Query.session_id == session_id)
                    .where(Query.client_message_id == client_message_id)
                )
                if existing_q:
                    if existing_q.status == "completed":
                        # Return previously saved response
                        st = graph.get_state(config)
                        return to_api_response({}, st, existing_q.id)
                    elif existing_q.status == "llm_unavailable":
                        # Resume failed turn per E3
                        try:
                            out = graph.invoke(None, config)
                            st = graph.get_state(config)
                            return to_api_response(out, st, existing_q.id)
                        except LLMUnavailable as e:
                            save_llm_failure(session_id, existing_q.id, text, client_message_id)
                            raise HTTPException(status_code=503, detail=e.to_dict())

        # Step 4: Check pending interrupt (confirmation flow)
        state_snap = graph.get_state(config)
        if state_snap.interrupts:
            interrupt_val = state_snap.interrupts[0].value
            decision = classify_confirmation(text, interrupt_val)

            proposal = interrupt_val.get("proposal") or {}
            orig_query_id = proposal.get("id") or state_snap.values.get("query_id")

            try:
                out = graph.invoke(Command(resume=decision), config)
                new_snap = graph.get_state(config)
                return to_api_response(out, new_snap, orig_query_id)
            except LLMUnavailable as e:
                save_llm_failure(session_id, orig_query_id, text, client_message_id)
                raise HTTPException(status_code=503, detail=e.to_dict())

        # Step 5: Check failed earlier turn (state.next non-empty)
        if state_snap.next:
            with session_scope() as session:
                old_queries = session.scalars(
                    select(Query)
                    .where(Query.session_id == session_id)
                    .where(Query.status.in_(["received", "running", "awaiting_confirmation"]))
                ).all()
                for oq in old_queries:
                    oq.status = "abandoned"

            # Clean open tool calls per E7/E8
            last_msgs = state_snap.values.get("messages", [])
            if last_msgs:
                last_m = last_msgs[-1]
                calls = getattr(last_m, "tool_calls", None) or []
                for c in calls:
                    repair = ToolMessage(content="error: earlier turn abandoned", tool_call_id=c["id"])
                    graph.update_state(config, {"messages": [repair]}, as_node="agent")

        # Step 6: Normal turn execution
        turn_id = str(uuid.uuid4())
        query_id = str(uuid.uuid4())

        with session_scope() as session:
            q = Query(
                id=query_id,
                session_id=session_id,
                user_id=user_id,
                query_text=text,
                status="received",
                turn_id=turn_id,
                client_message_id=client_message_id,
                parameters={},
            )
            session.add(q)
            session.commit()

        init_input = {
            "messages": [HumanMessage(content=text)],
            "user_id": user_id,
            "user_role": user_role,
            "department_id": department_id,
            "session_id": session_id,
            "query_id": query_id,
            "turn_id": turn_id,
            "tool_steps": 0,
            "confirmed": False,
        }

        try:
            out = graph.invoke(init_input, config)
            snap_after = graph.get_state(config)

            # Step 7: Interrupt pending after invoke
            if snap_after.interrupts:
                save_paused_turn(snap_after.values, client_message_id=client_message_id)
                return to_api_response(out, snap_after, query_id)

            return to_api_response(out, snap_after, query_id)

        except LLMUnavailable as e:
            save_llm_failure(session_id, query_id, text, client_message_id=client_message_id)
            raise HTTPException(status_code=503, detail=e.to_dict())

        except Exception as exc:
            logger.error("Unhandled error in agent run_turn: %s", exc, exc_info=True)
            with session_scope() as session:
                failed_q = session.get(Query, query_id)
                if failed_q:
                    failed_q.status = "failed"
            raise HTTPException(
                status_code=500,
                detail={"error": {"code": "INTERNAL_ERROR", "message": str(exc)}},
            )


# ---------------------------------------------------------------------------
# Event Turn Execution: run_event_turn (P11.10)
# ---------------------------------------------------------------------------

def run_event_turn(session_id: str, job_id: str) -> None:
    """
    Executes an asynchronous system event turn when a scrape job completes.
    Complies with Phase P11.10 and Experiment E10.
    """
    graph = get_compiled_graph()
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": getattr(settings, "RECURSION_LIMIT", 25),
    }

    with session_lock(session_id):
        snap = graph.get_state(config)
        # Skip event turn if session is waiting for user confirmation
        if snap.interrupts:
            logger.info("Skipping event turn for session %s: pending interrupt active.", session_id)
            return

        from Database.models.job import Job
        summary_payload = {}
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job:
                summary_payload = {
                    "job_id": job.id,
                    "status": job.status,
                    "records_found": job.records_found,
                    "verified_count": job.verified_count,
                    "duplicates_count": job.duplicates_count,
                }

        evt_message = HumanMessage(
            content=f"[JOB EVENT] {json.dumps(summary_payload)}",
            additional_kwargs={"hidden": True},
        )

        try:
            out = graph.invoke(
                {
                    "messages": [evt_message],
                    "event_job_id": job_id,
                },
                config,
            )
            final_snap = graph.get_state(config)
            # Find the notification message
            msgs = final_snap.values.get("messages", [])
            reply_text = ""
            for m in reversed(msgs):
                if getattr(m, "type", None) == "ai":
                    reply_text = getattr(m, "content", "")
                    break

            save_event_turn(session_id, job_id, query_id=None, reply_text=reply_text)

        except LLMUnavailable:
            logger.warning("LLM unavailable during event turn for job %s; leaving unseen.", job_id)
        except Exception as e:
            logger.error("Error executing event turn for job %s: %s", job_id, e, exc_info=True)
