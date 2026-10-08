"""Agent job tools use the same subscriber policy as the HTTP API."""
from typing import Annotated, Optional
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import select
from fastapi import HTTPException
from Database.controller import session_scope
from Database.models.job import Job
from Database.models.user import User
from services.visibility import apply_job_scope, is_job_visible
from services.jobs import cancel_visible_job, resume_visible_job, job_status_data
from routes.serializers import serialize_job


def current_account(db, state):
    user = db.get(User, (state or {}).get('user_id'))
    if not user or user.status != 'Active':
        raise HTTPException(401, 'Account is inactive.')
    return user


@tool
def get_job_status(job_id: Optional[str] = None, state: Annotated[dict, InjectedState] = None) -> dict:
    """Read your own or subscribed jobs; admins may read every job."""
    with session_scope() as db:
        user = current_account(db, state)
        if job_id:
            job = db.get(Job, job_id)
            return job_status_data(db, job) if job and is_job_visible(job, user, db) else {'error': 'Job not found.'}
        jobs = db.scalars(apply_job_scope(select(Job), user).order_by(Job.created_at.desc()).limit(5)).all()
        return {'jobs': [job_status_data(db, job) for job in jobs], 'count': len(jobs)}


@tool
def resume_job(job_id: str, state: Annotated[dict, InjectedState] = None) -> dict:
    """Resume a subscribed job after manually solving its verification challenge."""
    with session_scope() as db:
        try:
            return resume_visible_job(db, db.get(Job, job_id), current_account(db, state))
        except HTTPException as exc:
            return {'error': exc.detail, 'status': exc.status_code}


@tool
def cancel_job(job_id: str, state: Annotated[dict, InjectedState] = None) -> dict:
    """Cancel your unshared job. Only an admin may cancel a shared job."""
    with session_scope() as db:
        try:
            return cancel_visible_job(db, db.get(Job, job_id), current_account(db, state))
        except HTTPException as exc:
            return {'error': exc.detail, 'status': exc.status_code}
