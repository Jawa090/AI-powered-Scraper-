"""
agents/graph/tools/jobs.py
───────────────────────────
Job status, resume, and cancellation tools for the LangGraph agent.
Complies with Phase P11.5 and Decision D9 scoping.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from sqlalchemy import or_, select

logger = logging.getLogger(__name__)


def _serialize_job(job) -> Dict[str, Any]:
    """Serialize a Job ORM entity into a compact dictionary."""
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "progress": job.progress or 0,
        "script_id": job.script_id,
        "records_found": job.records_found or 0,
        "verified_count": job.verified_count or 0,
        "duplicates_count": job.duplicates_count or 0,
        "waiting_for": getattr(job, "waiting_for", None),
        "error_message": getattr(job, "error_message", None),
        "cancel_requested": getattr(job, "cancel_requested", False),
        "resume_requested": getattr(job, "resume_requested", False),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@tool
def get_job_status(
    job_id: Optional[str] = None,
    state: Annotated[dict, InjectedState] = None,
) -> Dict[str, Any]:
    """Get the status of scraping jobs, scoped to your own jobs.

    Args:
        job_id: Optional specific job ID to inspect.

    Returns:
        Dict with job status, progress, waiting state, and record counts.
    """
    from Database.controller import session_scope
    from Database.models.job import Job

    st = state or {}
    user_id = st.get("user_id")
    user_role = st.get("user_role", "user")

    try:
        with session_scope() as session:
            if job_id:
                job = session.get(Job, job_id)
                if not job:
                    return {"error": f"Job '{job_id}' not found."}
                if user_role != "admin" and user_id and job.created_by != user_id:
                    return {"error": f"Job '{job_id}' not found."}
                return _serialize_job(job)
            else:
                stmt = select(Job).order_by(Job.created_at.desc())
                if user_role != "admin" and user_id:
                    stmt = stmt.where(Job.created_by == user_id)
                stmt = stmt.limit(5)
                jobs = list(session.scalars(stmt).all())
                return {"jobs": [_serialize_job(j) for j in jobs], "count": len(jobs)}
    except Exception as e:
        logger.error("get_job_status error: %s", e)
        return {"error": str(e)}


@tool
def resume_job(
    job_id: str,
    state: Annotated[dict, InjectedState] = None,
) -> Dict[str, Any]:
    """Resume a job that is currently paused waiting for user input (e.g. CAPTCHA solved).

    Args:
        job_id: Unique ID of the job to resume.

    Returns:
        Dict confirming the resume request.
    """
    from Database.controller import session_scope
    from Database.models.job import Job

    st = state or {}
    user_id = st.get("user_id")
    user_role = st.get("user_role", "user")

    try:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                return {"error": f"Job '{job_id}' not found."}
            if user_role != "admin" and user_id and job.created_by != user_id:
                return {"error": f"Job '{job_id}' not found."}

            job.resume_requested = True
            session.commit()
            return {
                "job_id": job.id,
                "status": job.status,
                "resume_requested": True,
                "message": f"Resume requested for job '{job_id}'.",
            }
    except Exception as e:
        logger.error("resume_job error: %s", e)
        return {"error": str(e)}


@tool
def cancel_job(
    job_id: str,
    state: Annotated[dict, InjectedState] = None,
) -> Dict[str, Any]:
    """Request cancellation of an active scraping job.

    Args:
        job_id: Unique ID of the job to cancel.

    Returns:
        Dict confirming the cancellation request.
    """
    from Database.controller import session_scope
    from Database.models.job import Job

    st = state or {}
    user_id = st.get("user_id")
    user_role = st.get("user_role", "user")

    try:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if not job:
                return {"error": f"Job '{job_id}' not found."}
            if user_role != "admin" and user_id and job.created_by != user_id:
                return {"error": f"Job '{job_id}' not found."}

            job.cancel_requested = True
            session.commit()
            return {
                "job_id": job.id,
                "status": job.status,
                "cancel_requested": True,
                "message": f"Cancellation requested for job '{job_id}'.",
            }
    except Exception as e:
        logger.error("cancel_job error: %s", e)
        return {"error": str(e)}
