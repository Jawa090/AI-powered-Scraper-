from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from typing import Any, Dict, List

from sqlalchemy import select, func
from Database.controller import session_scope
from Database.models.job import Job
from Database.models.user import User
from services.auth import get_current_user
from services.visibility import apply_job_scope, is_job_visible, is_admin
from routes.serializers import serialize_job
from services.jobs import job_status_data

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

@router.get("")
def list_jobs(page: int = QueryParam(1, ge=1), pageSize: int = QueryParam(100, ge=1, le=100), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Returns list of all scraper jobs (both active and completed)."""
    with session_scope() as session:
        stmt = select(Job).order_by(Job.created_at.desc(), Job.id)
        stmt = apply_job_scope(stmt, current_user)
        total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        db_jobs = session.scalars(stmt.offset((page-1)*pageSize).limit(pageSize)).all()
        return {"jobs": [serialize_job(j) for j in db_jobs], "total": total, "page": page, "pageSize": pageSize}

@router.get("/{job_id}")
def get_job(job_id: str, current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Returns real-time status, progress, records count, and logs for a job."""
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job and is_job_visible(job, current_user, session):
            return {"job": job_status_data(session, job)}
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, current_user: User = Depends(get_current_user)):
    from services.jobs import cancel_visible_job
    with session_scope() as session:
        return cancel_visible_job(session, session.get(Job, job_id), current_user)


@router.post("/{job_id}/resume")
def resume_job(job_id: str, current_user: User = Depends(get_current_user)):
    from services.jobs import resume_visible_job
    with session_scope() as session:
        return resume_visible_job(session, session.get(Job, job_id), current_user)
