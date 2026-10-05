"""
routes/admin.py
───────────────
Phase 9 — Admin Panel API endpoints.

All endpoints require role == "admin"; non-admins get 403.
Provides paginated request logs, per-user timelines, and aggregate stats.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, and_, or_
from sqlalchemy.orm import selectinload

from Database import db as _db
from Database.models.query import Query
from Database.models.job import Job
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.action import AgentAction
from Database.models.lead import Lead
from Database.models.dataset import Dataset
from services.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# GET /api/admin/requests — Paginated request log
# ---------------------------------------------------------------------------

@router.get("/requests")
def list_requests(
    current_user: User = Depends(require_admin),
    user_id: Optional[str] = QueryParam(None, description="Filter by user ID"),
    decision: Optional[str] = QueryParam(None, description="Filter by decision (USE_DATABASE, NEED_FETCH, etc.)"),
    source: Optional[str] = QueryParam(None, description="Filter by source/script ID"),
    from_date: Optional[str] = QueryParam(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = QueryParam(None, alias="to", description="End date (YYYY-MM-DD)"),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Paginated log of all user requests/queries with decision info."""
    session = _db.session
    stmt = select(Query).options(
        selectinload(Query.user),
    ).order_by(Query.created_at.desc())

    conditions = []
    if user_id:
        conditions.append(Query.user_id == user_id)
    if decision:
        conditions.append(Query.decision == decision)
    if source:
        conditions.append(Query.source_id == source)
    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append(Query.created_at >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'from' date format. Use YYYY-MM-DD.")
    if to_date:
        try:
            dt = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append(Query.created_at <= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'to' date format. Use YYYY-MM-DD.")

    if conditions:
        stmt = stmt.where(and_(*conditions))

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    queries = list(session.scalars(stmt).all())

    items = []
    for q in queries:
        items.append({
            "id": q.id,
            "userId": q.user_id,
            "userName": q.user.name if q.user else None,
            "sessionId": q.session_id,
            "queryText": q.query_text,
            "parameters": q.parameters,
            "decision": q.decision,
            "status": q.status,
            "jobId": q.job_id,
            "recordsReturned": q.records_returned,
            "recordsNew": q.records_new,
            "recordsUpdated": q.records_updated,
            "servedAt": q.served_at.isoformat() if q.served_at else None,
            "createdAt": q.created_at.isoformat() if q.created_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/requests/{id} — Single request detail
# ---------------------------------------------------------------------------

@router.get("/requests/{request_id}")
def get_request_detail(
    request_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Full detail for a single request: query, decision, job, rows served, transcript."""
    session = _db.session
    query = session.get(Query, request_id)
    if not query:
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found.")

    # Get related job
    job_data = None
    if query.job_id:
        job = session.get(Job, query.job_id)
        if job:
            job_data = {
                "id": job.id,
                "name": job.name,
                "status": job.status,
                "progress": job.progress,
                "scriptId": job.script_id,
                "recordsFound": job.records_found,
                "verifiedCount": job.verified_count,
                "duplicatesCount": job.duplicates_count,
                "errorMessage": job.error_message,
                "startedAt": job.started_at.isoformat() if job.started_at else None,
                "completedAt": job.completed_at.isoformat() if job.completed_at else None,
            }

    # Get session messages (transcript) if session exists
    transcript = []
    if query.session_id:
        msg_stmt = (
            select(AgentMessage)
            .where(AgentMessage.session_id == query.session_id)
            .order_by(AgentMessage.created_at.asc())
        )
        messages = list(session.scalars(msg_stmt).all())
        for m in messages:
            transcript.append({
                "id": m.id,
                "sender": m.sender,
                "text": m.text,
                "toolTrace": getattr(m, "tool_trace", None),
                "createdAt": m.created_at.isoformat() if m.created_at else None,
            })

    # Get query_results (exact rows served)
    rows_served = []
    try:
        from Database.models.query_result import QueryResult
        qr_stmt = (
            select(QueryResult)
            .where(QueryResult.query_id == request_id)
            .order_by(QueryResult.rank.asc())
        )
        qr_results = list(session.scalars(qr_stmt).all())
        for qr in qr_results:
            lead = session.get(Lead, qr.lead_id) if qr.lead_id else None
            rows_served.append({
                "leadId": qr.lead_id,
                "rank": qr.rank,
                "company": lead.organization.name if lead and lead.organization else None,
                "contact": lead.contact.full_name if lead and lead.contact else None,
                "title": lead.title if lead else None,
            })
    except Exception:
        pass  # query_results table may not exist yet

    return {
        "request": {
            "id": query.id,
            "userId": query.user_id,
            "sessionId": query.session_id,
            "queryText": query.query_text,
            "parameters": query.parameters,
            "decision": query.decision,
            "status": query.status,
            "recordsReturned": query.records_returned,
            "recordsNew": query.records_new,
            "recordsUpdated": query.records_updated,
            "servedAt": query.served_at.isoformat() if query.served_at else None,
            "createdAt": query.created_at.isoformat() if query.created_at else None,
        },
        "job": job_data,
        "transcript": transcript,
        "rowsServed": rows_served,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/users/{id}/requests — Per-user timeline
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}/requests")
def get_user_requests(
    user_id: str,
    current_user: User = Depends(require_admin),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Per-user request timeline."""
    session = _db.session

    # Verify user exists
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")

    stmt = (
        select(Query)
        .where(Query.user_id == user_id)
        .order_by(Query.created_at.desc())
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

    offset = (page - 1) * page_size
    queries = list(session.scalars(stmt.offset(offset).limit(page_size)).all())

    items = []
    for q in queries:
        items.append({
            "id": q.id,
            "queryText": q.query_text,
            "decision": q.decision,
            "status": q.status,
            "jobId": q.job_id,
            "recordsReturned": q.records_returned,
            "createdAt": q.created_at.isoformat() if q.created_at else None,
        })

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/stats — Aggregate statistics
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_admin_stats(
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Aggregate statistics: DB-served vs scraped, duplicates prevented, failures, top segments."""
    session = _db.session

    # Total queries
    total_queries = session.scalar(select(func.count(Query.id))) or 0

    # Decision breakdown
    db_served = session.scalar(
        select(func.count(Query.id)).where(Query.decision == "USE_DATABASE")
    ) or 0
    scraped = session.scalar(
        select(func.count(Query.id)).where(Query.decision.in_(["NEED_FETCH", "PARTIAL"]))
    ) or 0
    clarifications = session.scalar(
        select(func.count(Query.id)).where(Query.decision == "NEED_CLARIFICATION")
    ) or 0

    # Job stats
    total_jobs = session.scalar(select(func.count(Job.id))) or 0
    completed_jobs = session.scalar(
        select(func.count(Job.id)).where(Job.status == "Completed")
    ) or 0
    failed_jobs = session.scalar(
        select(func.count(Job.id)).where(Job.status == "Failed")
    ) or 0

    # Duplicates prevented (sum of duplicates_count across all jobs)
    duplicates_prevented = session.scalar(
        select(func.coalesce(func.sum(Job.duplicates_count), 0))
    ) or 0

    # Total leads
    total_leads = session.scalar(select(func.count(Lead.id))) or 0

    # Total datasets
    total_datasets = session.scalar(select(func.count(Dataset.id))) or 0

    # Total users
    total_users = session.scalar(select(func.count(User.id))) or 0

    # Top scraper sources by job count
    top_sources_stmt = (
        select(Job.script_id, func.count(Job.id).label("job_count"))
        .group_by(Job.script_id)
        .order_by(func.count(Job.id).desc())
        .limit(10)
    )
    top_sources = [
        {"source": row[0], "jobCount": row[1]}
        for row in session.execute(top_sources_stmt).all()
    ]

    return {
        "totalQueries": total_queries,
        "decisions": {
            "dbServed": db_served,
            "scraped": scraped,
            "clarifications": clarifications,
        },
        "jobs": {
            "total": total_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
        },
        "duplicatesPrevented": duplicates_prevented,
        "totalLeads": total_leads,
        "totalDatasets": total_datasets,
        "totalUsers": total_users,
        "topSources": top_sources,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/requests/export.csv — Streamed CSV export
# ---------------------------------------------------------------------------

@router.get("/requests/export.csv")
def export_requests_csv(
    current_user: User = Depends(require_admin),
    user_id: Optional[str] = QueryParam(None),
    decision: Optional[str] = QueryParam(None),
    from_date: Optional[str] = QueryParam(None, alias="from"),
    to_date: Optional[str] = QueryParam(None, alias="to"),
):
    """Stream all matching requests as a CSV file."""
    session = _db.session
    stmt = select(Query).options(
        selectinload(Query.user),
    ).order_by(Query.created_at.desc())

    conditions = []
    if user_id:
        conditions.append(Query.user_id == user_id)
    if decision:
        conditions.append(Query.decision == decision)
    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append(Query.created_at >= dt)
        except ValueError:
            pass
    if to_date:
        try:
            dt = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append(Query.created_at <= dt)
        except ValueError:
            pass

    if conditions:
        stmt = stmt.where(and_(*conditions))

    queries = list(session.scalars(stmt).all())

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "User ID", "User Name", "Query Text", "Decision",
            "Status", "Job ID", "Records Returned", "Records New",
            "Records Updated", "Served At", "Created At",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for q in queries:
            writer.writerow([
                q.id,
                q.user_id,
                q.user.name if q.user else "",
                q.query_text or "",
                q.decision or "",
                q.status or "",
                q.job_id or "",
                q.records_returned or "",
                q.records_new or "",
                q.records_updated or "",
                q.served_at.isoformat() if q.served_at else "",
                q.created_at.isoformat() if q.created_at else "",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=requests_export.csv"},
    )
