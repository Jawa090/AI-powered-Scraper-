"""
routes/bot.py
─────────────
Chat and confirmation endpoints for the AI Agent Bot.
Implements Phase P11.11 / P12:
- POST /api/bot/chat: conversational turn via run_turn
- POST /api/bot/confirm: approval/rejection classified through LLM
- POST /api/bot/confirm-and-generate: resumes graph or returns 409 if no pending interrupt
- GET  /api/bot/sessions: list user's sessions (scoped per D9)
- GET  /api/bot/sessions/{id}/messages: poll messages excluding hidden event messages
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from Database import get_db
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from services.auth import get_current_user
from services.visibility import apply_session_scope, is_admin
from agents.graph.runner import run_turn, pending_interrupt, _get_lock
from agents.graph.graph import get_compiled_graph
from routes.serializers import serialize_session, serialize_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["AI Bot"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class BotChatRequest(BaseModel):
    sessionId: str = Field(..., min_length=1, max_length=255, description="Session identifier")
    message: str = Field(..., min_length=1, max_length=10000, description="User message text")
    clientMessageId: Optional[str] = Field(default=None, description="Optional client message ID")
    currentRequirement: Optional[Dict[str, Any]] = Field(default=None, description="Optional current requirement state")


class BotConfirmRequest(BaseModel):
    sessionId: str = Field(..., min_length=1, max_length=255, description="Session identifier")
    decision: str = Field(..., description="approve or reject")
    clientMessageId: Optional[str] = Field(default=None, description="Optional client message ID")


class BotConfirmAndGenerateRequest(BaseModel):
    sessionId: str = Field(..., min_length=1, max_length=255, description="Session identifier")
    requirement: Optional[Dict[str, Any]] = Field(default=None, description="Requirement dictionary")
    preferredScriptId: Optional[str] = Field(default=None, max_length=50, description="Optional preferred script identifier")


# ---------------------------------------------------------------------------
# Chat Endpoint
# ---------------------------------------------------------------------------

@router.post("/chat")
def bot_chat(
    req: BotChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Multi-turn conversational agent endpoint (LangGraph v2)."""
    # Verify or initialize session
    sess = db.get(AgentSession, req.sessionId)
    if sess:
        if sess.user_id != current_user.id and not is_admin(current_user):
            raise HTTPException(status_code=403, detail="Session does not belong to you.")
    else:
        # Create session if not already existing
        sess = AgentSession(
            id=req.sessionId,
            user_id=current_user.id,
            department_id=getattr(current_user, "department_id", None) or "dept-default",
            agent_id="agent-master",
            title=req.message[:50] if req.message else "New Session",
            status="active",
        )
        db.add(sess)
        db.commit()

    # Persist user message
    user_msg = AgentMessage(
        session_id=req.sessionId,
        sender="user",
        role="user",
        text=req.message,
        message_metadata={"clientMessageId": req.clientMessageId} if req.clientMessageId else None,
    )
    db.add(user_msg)
    db.commit()

    # Execute agent turn
    result = run_turn(current_user, req.sessionId, req.message)

    # Persist agent reply
    reply_text = result.get("reply") or ""
    agent_msg = AgentMessage(
        session_id=req.sessionId,
        sender="agent",
        role="agent",
        text=reply_text,
        suggestions=result.get("suggestions"),
        message_metadata={
            "pendingAction": result.get("pendingAction"),
            "jobId": result.get("jobId"),
            "degraded": result.get("degraded", False),
        },
    )
    db.add(agent_msg)
    db.commit()

    return result


# ---------------------------------------------------------------------------
# Confirmation Endpoint
# ---------------------------------------------------------------------------

@router.post("/confirm")
def bot_confirm(
    req: BotConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Submits user approval/rejection decision through the agent turn.
    Sends standard approval/rejection prompt which the LLM classifies.
    """
    sess = db.get(AgentSession, req.sessionId)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session '{req.sessionId}' not found.")
    if sess.user_id != current_user.id and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Session does not belong to you.")

    # Determine standard phrasing for LLM classification
    decision_clean = req.decision.strip().lower()
    if decision_clean in ["approve", "yes", "confirm"]:
        text = "Yes, run the proposed scrape."
    else:
        text = "No, don't run it."

    # Persist user confirmation choice
    user_msg = AgentMessage(
        session_id=req.sessionId,
        sender="user",
        role="user",
        text=text,
        message_metadata={
            "decision": req.decision,
            "clientMessageId": req.clientMessageId,
        },
    )
    db.add(user_msg)
    db.commit()

    # Execute turn
    result = run_turn(current_user, req.sessionId, text)

    # Persist agent reply
    agent_msg = AgentMessage(
        session_id=req.sessionId,
        sender="agent",
        role="agent",
        text=result.get("reply", ""),
        suggestions=result.get("suggestions"),
        message_metadata={
            "jobId": result.get("jobId"),
            "pendingAction": result.get("pendingAction"),
        },
    )
    db.add(agent_msg)
    db.commit()

    return result


# ---------------------------------------------------------------------------
# Confirm-and-Generate (Legacy Stepper / Resume Endpoint)
# ---------------------------------------------------------------------------

@router.post("/confirm-and-generate")
def bot_confirm_and_generate(
    req: BotConfirmAndGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Resumes the LangGraph interrupt.
    Returns 409 {success: false} if no interrupt is pending.
    """
    sess = db.get(AgentSession, req.sessionId)
    if sess:
        if sess.user_id != current_user.id and not is_admin(current_user):
            raise HTTPException(status_code=403, detail="Session does not belong to you.")

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": req.sessionId}, "recursion_limit": 25}

    if not pending_interrupt(graph, config):
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "message": "No pending confirmation to resume.",
            },
        )

    # Submit approval text through the chat path
    approval_text = "Yes, run the proposed scrape."
    if sess:
        user_msg = AgentMessage(
            session_id=req.sessionId,
            sender="user",
            role="user",
            text=approval_text,
        )
        db.add(user_msg)
        db.commit()

    result = run_turn(current_user, req.sessionId, approval_text)
    state = graph.get_state(config).values
    job_id = state.get("job_id") or result.get("jobId")
    script_id = state.get("slots", {}).get("source") or req.preferredScriptId or "auto"
    dataset_id = state.get("dataset_id")

    if sess:
        agent_msg = AgentMessage(
            session_id=req.sessionId,
            sender="agent",
            role="agent",
            text=result.get("reply", ""),
            message_metadata={
                "jobId": job_id,
                "scriptId": script_id,
                "datasetId": dataset_id,
            },
        )
        db.add(agent_msg)
        db.commit()

    return {
        "success": bool(job_id),
        "jobId": job_id,
        "scriptId": script_id,
        "datasetId": dataset_id,
        "message": "Scraper initialized successfully." if job_id else "No job was generated.",
    }


# ---------------------------------------------------------------------------
# Sessions Endpoint
# ---------------------------------------------------------------------------

@router.get("/sessions")
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Returns the user's own agent sessions (admin sees all per D9)."""
    stmt = select(AgentSession).order_by(AgentSession.created_at.desc())
    stmt = apply_session_scope(stmt, current_user)
    sessions = list(db.scalars(stmt).all())
    return {
        "sessions": [serialize_session(s) for s in sessions],
    }


# ---------------------------------------------------------------------------
# Session Messages Polling Endpoint
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    after: Optional[str] = QueryParam(None, description="ISO timestamp to filter messages created after"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Returns messages for a session.
    Owner only (or admin); excludes hidden messages.
    Supports polling via 'after' parameter.
    """
    sess = db.get(AgentSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    if sess.user_id != current_user.id and not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Session does not belong to you.")

    stmt = (
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.created_at.asc())
    )

    if after:
        try:
            clean_after = after.strip().replace("Z", "+00:00")
            if " " in clean_after and "+" not in clean_after:
                parts = clean_after.rsplit(" ", 1)
                if len(parts) == 2 and ":" in parts[1]:
                    clean_after = f"{parts[0]}+{parts[1]}"
            after_dt = datetime.fromisoformat(clean_after)
            stmt = stmt.where(AgentMessage.created_at > after_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ISO timestamp format for 'after'.")

    messages = list(db.scalars(stmt).all())

    # Filter out hidden event messages for normal user polling
    visible_messages = []
    for m in messages:
        meta = m.message_metadata if isinstance(m.message_metadata, dict) else {}
        is_hidden = meta.get("hidden") is True or m.role in ["hidden", "system_event"]
        if not is_hidden:
            visible_messages.append(serialize_message(m))

    return {
        "sessionId": session_id,
        "messages": visible_messages,
    }
