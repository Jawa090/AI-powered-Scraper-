"""Authenticated chat, approval, durable completion and conversation history."""
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from Database import get_db
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.query import Query
from Database.models.job import Job
from services.auth import get_current_user
from services.visibility import is_admin, is_job_visible
from services.sessions import reset_session
from agents.graph.runner import run_turn, run_event_turn
from agents.graph.graph import get_compiled_graph
from routes.serializers import serialize_message, serialize_session

router = APIRouter(prefix="/api/bot", tags=["AI Bot"])


class BotChatRequest(BaseModel):
    sessionId: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=10000)
    clientMessageId: str | None = Field(default=None, max_length=100)
    currentRequirement: dict[str, Any] | None = None
    newOnly: bool = False
    expectedProposalId: str | None = Field(default=None, max_length=200)


class BotConfirmRequest(BaseModel):
    sessionId: str
    decision: str
    clientMessageId: str | None = None
    expectedProposalId: str | None = Field(default=None, max_length=200)


class BotChatNewRequest(BaseModel):
    previousSessionId: str | None = None


def owned_session(db, sid, user):
    row = db.get(AgentSession, sid)
    if not row or (row.user_id != user.id and not is_admin(user)):
        raise HTTPException(404, "Session not found.")
    return row


@router.post("/chat/new")
def bot_chat_new(req: BotChatNewRequest, current_user=Depends(get_current_user)):
    return reset_session(current_user, req.previousSessionId)


@router.post("/chat")
def bot_chat(req: BotChatRequest, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    sess = db.get(AgentSession, req.sessionId)
    if sess and sess.user_id != current_user.id:
        raise HTTPException(403, 'Only the conversation owner can send messages.')
    return run_turn(current_user, req.sessionId, req.message, req.clientMessageId,
        new_only=req.newOnly, expected_proposal_id=req.expectedProposalId)


@router.post("/confirm")
def bot_confirm(req: BotConfirmRequest, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    sess = owned_session(db, req.sessionId, current_user)
    if sess.user_id != current_user.id:
        raise HTTPException(403, "Only the conversation owner can approve it.")
    if req.decision not in ("approve", "reject"):
        raise HTTPException(422, "Decision must be approve or reject.")
    snap = get_compiled_graph().get_state({"configurable": {"thread_id": req.sessionId}})
    # Idempotent retries may arrive after the interrupt has completed.
    previous = db.scalar(select(Query).where(Query.session_id == req.sessionId,
        Query.client_message_id == req.clientMessageId)) if req.clientMessageId else None
    if not snap.interrupts and not previous:
        raise HTTPException(409, "There is no pending scrape proposal.")
    return run_turn(current_user, req.sessionId,
        "Yes, run the proposed scrape." if req.decision == "approve" else "No, do not run it.",
        req.clientMessageId, expected_proposal_id=req.expectedProposalId)


@router.get("/sessions")
def sessions(current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    rows = db.scalars(select(AgentSession).where(AgentSession.user_id == current_user.id).order_by(AgentSession.updated_at.desc())).all()
    return {"sessions": [serialize_session(row) for row in rows]}


@router.get("/sessions/{session_id}/messages")
def messages(session_id: str, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    owned_session(db, session_id, current_user)
    rows = db.scalars(select(AgentMessage).where(AgentMessage.session_id == session_id,
        AgentMessage.message_metadata['collectionCancelled'].as_boolean().is_not(True)).order_by(AgentMessage.created_at, AgentMessage.id)).all()
    return {"messages": [serialize_message(row) for row in rows]}


@router.get("/state")
def bot_state(sessionId: str, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    sess = owned_session(db, sessionId, current_user)
    if sess.status != 'active':
        return {'pendingAction': None, 'proposedActions': [], 'activeJobId': None, 'pendingEventJobIds': []}
    snap = get_compiled_graph().get_state({"configurable": {"thread_id": sessionId}})
    pending = snap.interrupts[0].value if snap.interrupts else None
    from Database.models.session_event import SessionEvent
    job = db.scalar(select(Job).join(Query, Query.job_id == Job.id).where(Query.session_id == sessionId,
        Job.status.in_(["Queued", "Running", "WaitingForUser"])).order_by(Job.created_at.desc()))
    events = db.scalars(select(SessionEvent.job_id).where(SessionEvent.session_id == sessionId, SessionEvent.status == "pending")).all()
    proposal = (pending or {}).get("proposal") or {}
    return {"pendingAction": pending, "proposedActions": [{"actionType": "scrape",
        "label": proposal.get("question"), "parameters": proposal.get("args"), "requiresConfirmation": True}] if pending else [],
        "activeJobId": job.id if job else None, "pendingEventJobIds": list(events)}


@router.get('/cleared-recovery/{session_id}')
def cleared_recovery(session_id: str, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    # Compatibility for clients already polling: never expose cancellation receipts.
    sess = owned_session(db, session_id, current_user)
    if sess.user_id != current_user.id or sess.status != 'cleared':
        raise HTTPException(404, 'Cleared chat not found.')
    return {'pending': False, 'deliveries': []}



class JobUpdateRequest(BaseModel):
    sessionId: str
    jobId: str


@router.post("/job-update")
def bot_job_update(req: JobUpdateRequest, current_user=Depends(get_current_user), db: Session=Depends(get_db)):
    sess = owned_session(db, req.sessionId, current_user)
    job = db.get(Job, req.jobId)
    linked = db.scalar(select(Query.id).where(Query.session_id == req.sessionId, Query.job_id == req.jobId))
    if not job or not linked or sess.user_id != current_user.id or not is_job_visible(job, current_user, db):
        raise HTTPException(404, "Completion not found.")
    if job.status not in ("Completed", "Partial", "Failed", "Cancelled"):
        return {"status": job.status}
    return run_event_turn(req.sessionId, req.jobId)
