"""
agents/graph/tools/jobs.py
───────────────────────────
Job status tool for the LangGraph agent.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def get_job_status(job_id: Optional[str] = None) -> dict:
    """Get the status of a scraping job.

    If job_id is provided, returns that specific job's status.
    If job_id is omitted, returns the most recent jobs.

    Args:
        job_id: Optional specific job ID to check.

    Returns:
        Dict with job status, progress, and record counts.
    """
    from Database import db as _db
    from Database.models.job import Job
    from sqlalchemy import select

    try:
        if job_id:
            job = _db.session.get(Job, job_id)
            if not job:
                return {"error": f"Job '{job_id}' not found."}
            return _serialize_job(job)
        else:
            stmt = select(Job).order_by(Job.created_at.desc()).limit(5)
            jobs = list(_db.session.scalars(stmt).all())
            return {"jobs": [_serialize_job(j) for j in jobs], "count": len(jobs)}
    except Exception as e:
        logger.error("get_job_status tool error: %s", e, exc_info=True)
        return {"error": str(e)}


def _serialize_job(job) -> dict:
    """Serialize a Job ORM object to a compact dict."""
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "progress": job.progress or 0,
        "script_id": job.script_id,
        "records_found": job.records_found or 0,
        "verified_count": job.verified_count or 0,
        "duplicates_count": job.duplicates_count or 0,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
