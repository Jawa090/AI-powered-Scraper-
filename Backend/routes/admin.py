"""
routes/admin.py
───────────────
Phase 12 — Admin Panel API endpoints.

All endpoints require role == "admin"; non-admins get 403.
Provides:
- User management: CRUD for users per P3.4
- Paginated request log with source filtering via jobs.script_id and strict date validation
- Single request detail with selectinload (no N+1), slots, decision, KB state, transcript, ordered tool trace, rows served
- Per-user request timelines
- Admin chat viewer: user sessions and session messages (including hidden event messages)
- Aggregate stats: D10 counts, jobs by status, duplicates prevented, LLM-unavailable turns, KB usage
- Streamed CSV export with matching filters and validation
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_
from sqlalchemy.orm import selectinload, Session
from sqlalchemy.exc import IntegrityError

from Database import get_db
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.job import Job
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.message import AgentMessage
from Database.models.lead import Lead
from Database.models.organization import Organization
from Database.models.contact import Contact
from Database.models.dataset import Dataset
from services.auth import require_admin, hash_password
from settings import settings
from routes.serializers import serialize_job, serialize_session, serialize_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Pydantic Schemas for Admin User Management
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    username: str
    password: str
    role: Optional[str] = "user"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# User Management Endpoints (P3.4 / P12.3)
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(
    session: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> List[Dict[str, Any]]:
    """Returns all users with builtIn flag for env accounts."""
    db_users = session.query(User).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "status": u.status,
            "auth_source": u.auth_source,
            "builtIn": u.role == 'admin',
        }
        for u in db_users
    ]


@router.post("/users")
def create_user(
    req: UserCreate,
    session: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Create a new user. Role is forced to user; only one admin allowed."""
    if req.role == "admin":
        raise HTTPException(
            status_code=400,
            detail="Only one admin is allowed",
        )

    clean_username = req.username.strip().lower()
    email = (req.email or (clean_username if '@' in clean_username else '')).strip().lower()
    if not email or '@' not in email or '.' not in email.rsplit('@', 1)[1]:
        raise HTTPException(422, 'A valid user email is required.')
    if not clean_username or not req.password:
        raise HTTPException(422, 'Username and password are required.')
    if session.scalar(select(User.id).where(func.lower(User.username) == clean_username)):
        raise HTTPException(409, 'Username already exists.')
    if clean_username in [settings.AUTH_ADMIN_USERNAME.lower(), settings.AUTH_USER_USERNAME.lower()]:
        raise HTTPException(status_code=409, detail="Username conflicts with built-in env account")

    new_user = User(
        id=f"usr-{uuid.uuid4()}",
        name=req.name or req.username,
        username=clean_username,
        email=email,
        password_hash=hash_password(req.password),
        role="user",
        status="Active",
        auth_source="db",
        department_id="dept-default",
    )
    session.add(new_user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username already exists")

    return {"id": new_user.id, "message": "User created successfully"}


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    req: UserUpdate,
    session: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Update normal database users; protect the sole administrator."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == 'admin':
        raise HTTPException(400, 'The sole administrator account is protected.')

    if req.email is not None:
        email = req.email.strip().lower()
        if '@' not in email or '.' not in email.rsplit('@', 1)[1]:
            raise HTTPException(422, 'A valid user email is required.')
        user.email = email

    if req.name is not None:
        user.name = req.name
    if req.status is not None:
        if req.status not in ('Active', 'Disabled'):
            raise HTTPException(422, 'Status must be Active or Disabled.')
        user.status = req.status
    if req.password is not None and req.password != "":
        user.password_hash = hash_password(req.password)

    session.commit()
    return {"message": "User updated successfully"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    session: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Soft-disable user. Env users cannot be disabled."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == 'admin':
        raise HTTPException(400, 'The sole administrator account is protected.')

    user.status = "Disabled"
    session.commit()
    return {"message": "User disabled successfully"}


# ---------------------------------------------------------------------------
# Filter Helper for Requests
# ---------------------------------------------------------------------------

@router.get('/deliveries/export.csv')
def export_deliveries(session: Session = Depends(get_db), admin: User = Depends(require_admin),
    user_id: Optional[str] = None, query_id: Optional[str] = None):
    """Export exact recorded delivery values, with the same admin permission."""
    from services.delivery import delivery_rows
    stmt = select(Query).where(Query.served_at.isnot(None), Query.records_returned > 0,
        Query.parameters['collectionCancelled'].as_boolean().is_not(True)).order_by(Query.served_at, Query.id)
    if user_id: stmt = stmt.where(Query.user_id == user_id, Query.parameters['collectionCancelled'].as_boolean().is_not(True),
               Query.parameters['kind'].as_string().is_distinct_from('reset_receipt'))
    if query_id: stmt = stmt.where(Query.id == query_id)
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['User', 'Query ID', 'Request', 'Served At', 'Record ID', 'Company', 'Title', 'Category',
        'City', 'State', 'Email', 'Phone', 'Source', 'Source URL', 'Record Version', 'Historical Snapshot',
        'Request Fulfilled', 'Delivery Kind', 'Matching Records', 'Requested Records', 'Understood Request'])
    def csv_value(value):
        text = str(value if value is not None else '')
        return "'" + text if text.startswith(('=', '+', '-', '@')) else text
    for query in session.scalars(stmt):
        user = session.get(User, query.user_id)
        heading = 'admin' if user and user.role == 'admin' else (user.email or user.username if user else query.user_id)
        entries = session.scalars(select(QueryResult).where(QueryResult.query_id == query.id).order_by(QueryResult.rank, QueryResult.lead_id)).all()
        for row, entry in zip(delivery_rows(session, query.id), entries):
            writer.writerow([csv_value(v) for v in [heading, query.id, query.query_text, query.served_at.isoformat(),
                row['id'], row.get('company'), row.get('title'), row.get('category'), row.get('city'), row.get('state'),
                row.get('email'), row.get('phone'), row.get('sourceCode'), row.get('sourceUrl'), entry.record_version,
                entry.snapshot is not None, (query.parameters or {}).get('requestFulfilled'),
                (query.parameters or {}).get('deliveryKind'), (query.parameters or {}).get('matchingRecordsDelivered'),
                (query.parameters or {}).get('requestedRecords'), json.dumps((query.parameters or {}).get('slots', {}))]])
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=delivered_data.csv'})


@router.get('/deliveries')
def list_deliveries(session: Session = Depends(get_db), admin: User = Depends(require_admin),
    user_id: Optional[str] = None, page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(50, ge=1, le=200)):
    """Exact served values grouped by user email, including the administrator."""
    from services.delivery import delivery_rows
    users = session.scalars(select(User).order_by(User.role, User.email, User.id)).all()
    groups = []
    for user in users:
        if user_id and user.id != user_id:
            continue
        where = (Query.user_id == user.id, Query.served_at.isnot(None),
            Query.parameters['collectionCancelled'].as_boolean().is_not(True),
            or_(Query.records_returned > 0, Query.parameters['kind'].as_string() == 'event'))
        total = session.scalar(select(func.count(Query.id)).where(*where)) or 0
        requests = session.scalars(select(Query).where(*where).order_by(Query.served_at.desc(), Query.id)
            .offset((page - 1) * page_size).limit(page_size)).all()
        groups.append({'userId': user.id, 'email': user.email, 'username': user.username,
            'heading': 'admin' if user.role == 'admin' else (user.email or user.username + ' (email not set)'),
            'total': total, 'page': page, 'pageSize': page_size,
            'deliveries': [{'queryId': q.id, 'request': q.query_text,
                'servedAt': q.served_at.isoformat(), 'jobId': q.job_id, 'records': delivery_rows(session, q.id),
                'understoodRequest': (q.parameters or {}).get('slots', {}),
                **{key: (q.parameters or {}).get(key) for key in ('requestFulfilled', 'deliveryKind',
                    'matchingRecordsDelivered', 'requestedRecords', 'recoveredRecords', 'collectionCancelled', 'timedOut')},
                'snapshotAvailable': all(r.snapshot is not None for r in session.scalars(select(QueryResult).where(QueryResult.query_id == q.id)))} for q in requests]})
    return {'groups': groups}

def _build_requests_query(
    user_id: Optional[str],
    decision: Optional[str],
    source: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
):
    """Build SQLAlchemy query with filters, strict date parsing, and source filtering."""
    stmt = (
        select(Query)
        .options(
            selectinload(Query.user),
            selectinload(Query.session),
        )
        .order_by(Query.created_at.desc())
    )

    conditions = [Query.parameters['collectionCancelled'].as_boolean().is_not(True),
        Query.parameters['kind'].as_string().is_distinct_from('reset_receipt')]
    if user_id:
        conditions.append(Query.user_id == user_id)
    if decision:
        conditions.append(Query.decision == decision)
    if source:
        # The source filter goes through jobs.script_id or query.source_id
        stmt = stmt.outerjoin(Job, Query.job_id == Job.id)
        conditions.append(or_(Job.script_id == source, Query.source_id == source))

    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            conditions.append(Query.created_at >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'from' date format. Use YYYY-MM-DD.")

    if to_date:
        try:
            # Inclusive: < to_date + 1 day
            dt = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            conditions.append(Query.created_at < dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'to' date format. Use YYYY-MM-DD.")

    if conditions:
        stmt = stmt.where(and_(*conditions))

    return stmt


# ---------------------------------------------------------------------------
# Activity Log: GET /api/admin/requests
# ---------------------------------------------------------------------------

@router.get("/requests")
def list_requests(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    user_id: Optional[str] = QueryParam(None, description="Filter by user ID"),
    decision: Optional[str] = QueryParam(None, description="Filter by decision"),
    source: Optional[str] = QueryParam(None, description="Filter by source/script ID"),
    from_date: Optional[str] = QueryParam(None, alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = QueryParam(None, alias="to", description="End date (YYYY-MM-DD)"),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Paginated log of user queries with decision info, source filtering, and date bounds."""
    stmt = _build_requests_query(user_id, decision, source, from_date, to_date)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

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
            "parameters": q.parameters or {},
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
# Streamed CSV Export: GET /api/admin/requests/export.csv
# ---------------------------------------------------------------------------

@router.get("/requests/export.csv")
def export_requests_csv(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    user_id: Optional[str] = QueryParam(None),
    decision: Optional[str] = QueryParam(None),
    source: Optional[str] = QueryParam(None),
    from_date: Optional[str] = QueryParam(None, alias="from"),
    to_date: Optional[str] = QueryParam(None, alias="to"),
):
    """Streams matching user requests as a CSV file with identical filters and date validation."""
    stmt = _build_requests_query(user_id, decision, source, from_date, to_date)
    queries = list(session.scalars(stmt).all())

    def generate_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "User ID", "User Name", "Decision",
            "Status", "Job ID", "Records Returned", "Records New",
            "Records Updated", "Served At", "Created At",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for q in queries:
            writer.writerow([
                q.id,
                q.user_id or "",
                q.user.name if q.user else "",
                q.decision or "",
                q.status or "",
                q.job_id or "",
                q.records_returned if q.records_returned is not None else "",
                q.records_new if q.records_new is not None else "",
                q.records_updated if q.records_updated is not None else "",
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


# ---------------------------------------------------------------------------
# Request Details: GET /api/admin/requests/{id}
# ---------------------------------------------------------------------------

@router.get("/requests/{request_id}")
def get_request_detail(
    request_id: str,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Returns full detail for a single request:
    - query & parameters
    - slots
    - decision
    - KB state + hits
    - job (including errorMessage)
    - transcript for this query + job events
    - ordered tool trace
    - exact rows served via single selectinload query (no N+1)
    """
    query = session.get(Query, request_id)
    if not query or (query.parameters or {}).get('collectionCancelled'):
        raise HTTPException(status_code=404, detail=f"Request '{request_id}' not found.")

    # Related job details
    job_data = None
    if query.job_id:
        job = session.get(Job, query.job_id)
        if job:
            job_data = serialize_job(job)

    # Transcript from session messages (including hidden event messages)
    params = query.parameters if isinstance(query.parameters, dict) else {}
    ordered_tool_trace = params.get("trace", [])

    # Rows served loaded in a single query with selectinload (no N+1)
    qr_stmt = (
        select(QueryResult)
        .options(
            selectinload(QueryResult.lead).selectinload(Lead.organization),
            selectinload(QueryResult.lead).selectinload(Lead.contact),
        )
        .where(QueryResult.query_id == request_id)
        .order_by(QueryResult.rank.asc())
    )
    qr_results = list(session.scalars(qr_stmt).all())

    from routes.serializers import serialize_lead
    from services.delivery import delivery_rows
    rows_served = [{**row, 'leadId': row['id'], 'rank': index, 'contact': row.get('name')}
        for index, row in enumerate(delivery_rows(session, request_id))]
    transcript = session.scalars(select(AgentMessage).where(
        AgentMessage.session_id == query.session_id,
        AgentMessage.message_metadata['queryId'].as_string() == query.id
    ).order_by(AgentMessage.created_at, AgentMessage.id)).all()

    slots = params.get("slots", {})

    return {
        "request": {
            "id": query.id,
            "userId": query.user_id,
            "sessionId": query.session_id,
            "queryText": query.query_text,
            "parameters": params,
            "slots": slots,
            "decision": query.decision,
            "status": query.status,
            "jobId": query.job_id,
            "recordsReturned": query.records_returned,
            "recordsNew": query.records_new,
            "recordsUpdated": query.records_updated,
            "servedAt": query.served_at.isoformat() if query.served_at else None,
            "createdAt": query.created_at.isoformat() if query.created_at else None,
        },
        "slots": slots,
        "decision": query.decision,
        "kbState": params.get("kb_state"),
        "kbHits": params.get("kb_hit_ids", []),
        "job": job_data,
        "toolTrace": ordered_tool_trace,
        "transcript": [serialize_message(message) for message in transcript],
        "rowsServed": rows_served,
    }


# ---------------------------------------------------------------------------
# User Timeline: GET /api/admin/users/{id}/requests
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}/requests")
def get_user_requests(
    user_id: str,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Per-user request timeline."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")

    stmt = (
        select(Query)
        .where(Query.user_id == user_id, Query.parameters['collectionCancelled'].as_boolean().is_not(True),
               Query.parameters['kind'].as_string().is_distinct_from('reset_receipt'))
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
            "username": user.username,
            "role": user.role,
        },
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


# ---------------------------------------------------------------------------
# Sessions & Messages (Admin Viewer)
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}/sessions")
def get_user_sessions(
    user_id: str,
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Returns all sessions for a specific user."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")

    stmt = (
        select(AgentSession)
        .where(AgentSession.user_id == user_id)
        .order_by(AgentSession.created_at.desc())
    )
    sessions = list(session.scalars(stmt).all())
    return {
        "userId": user_id,
        "sessions": [serialize_session(s) for s in sessions],
    }





# ---------------------------------------------------------------------------
# Aggregate Statistics: GET /api/admin/stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_admin_stats(
    session: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Returns aggregate platform statistics:
    - D10 decision counts
    - jobs grouped by status
    - duplicates prevented
    - LLM-unavailable turns
    - KB usage
    """
    total_queries = session.scalar(select(func.count(Query.id))) or 0

    # D10 Decision Counts: KB, DB, SCRAPER, PARTIAL, CLARIFY, NONE, DECLINED, FAILED, LLM_UNAVAILABLE
    d10_decisions = [
        "KB", "DB", "SCRAPER", "PARTIAL", "CLARIFY",
        "NONE", "DECLINED", "FAILED", "LLM_UNAVAILABLE",
    ]
    d10_counts: Dict[str, int] = {k: 0 for k in d10_decisions}

    decision_rows = session.execute(
        select(Query.decision, func.count(Query.id)).group_by(Query.decision)
    ).all()

    for dec, count in decision_rows:
        if not dec:
            continue
        d_upper = dec.upper()
        if d_upper in d10_counts:
            d10_counts[d_upper] += count
        elif d_upper in ["USE_DATABASE"]:
            d10_counts["DB"] += count
        elif d_upper in ["NEED_FETCH"]:
            d10_counts["SCRAPER"] += count
        elif d_upper in ["NEED_CLARIFICATION"]:
            d10_counts["CLARIFY"] += count
        elif d_upper in ["USE_KB"]:
            d10_counts["KB"] += count
        else:
            d10_counts[d_upper] = count

    # Jobs grouped by status
    job_status_rows = session.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    ).all()
    jobs_by_status = {status: count for status, count in job_status_rows if status}
    total_jobs = sum(jobs_by_status.values())

    # Duplicates prevented
    duplicates_prevented = session.scalar(
        select(func.coalesce(func.sum(Job.duplicates_count), 0))
    ) or 0

    # LLM-unavailable turns
    llm_unavailable_turns = session.scalar(
        select(func.count(Query.id)).where(
            or_(Query.decision == "LLM_UNAVAILABLE", Query.status == "llm_unavailable")
        )
    ) or 0

    # KB usage count
    kb_usage = d10_counts.get("KB", 0)

    # Counts
    total_leads = session.scalar(select(func.count(Lead.id))) or 0
    total_datasets = session.scalar(select(func.count(Dataset.id))) or 0
    total_users = session.scalar(select(func.count(User.id))) or 0

    # Top sources
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
        "d10Counts": d10_counts,
        "decisions": d10_counts,  # Alias for backward compatibility
        "jobsByStatus": jobs_by_status,
        "jobs": {
            "total": total_jobs,
            "completed": jobs_by_status.get("Completed", 0),
            "failed": jobs_by_status.get("Failed", 0),
        },
        "duplicatesPrevented": duplicates_prevented,
        "llmUnavailableTurns": llm_unavailable_turns,
        "kbUsage": kb_usage,
        "totalLeads": total_leads,
        "totalDatasets": total_datasets,
        "totalUsers": total_users,
        "topSources": top_sources,
    }
