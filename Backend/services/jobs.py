"""
services/jobs.py
────────────────
Job enqueueing and validation service complying with Phase P7.1.
Provides enqueue_scrape() — the authoritative route to create scrape jobs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from Database.models.job import Job
from Database.models.query import Query
from Database.models.user import User
from scrappers.base import (
    InvalidScrapeParams,
    JobCancelled,
    ScraperException,
    ScraperNotReady,
    UnknownScraper,
)
from scrappers.controller import check_ready, get_meta, validate_params
from settings import settings

logger = logging.getLogger(__name__)


class ScrapeNotAllowed(ScraperException):
    """Raised when a scrape is requested for an unknown or unsupported scraper ID."""
    pass


class UserWaitTimeout(ScraperException):
    """Raised when a job waiting for user interaction times out."""
    pass


class WorkerShutdown(ScraperException):
    """Raised when worker receives SIGINT/SIGTERM during job execution."""
    pass


class ScraperNoDataTimeout(ScraperException):
    """No extracted records arrived within the five-minute watchdog window."""
    pass


def cancel_visible_job(session, job, user):
    """One subscriber cannot cancel collection needed by another subscriber."""
    from fastapi import HTTPException
    from services.visibility import is_admin, is_job_visible
    if not job or not is_job_visible(job, user, session):
        raise HTTPException(404, 'Job not found.')
    other = session.scalar(select(Query.id).where(Query.job_id == job.id,
        Query.user_id != user.id).limit(1))
    if not is_admin(user) and (job.created_by != user.id or other):
        raise HTTPException(409, 'Only an administrator can cancel a job shared with another user.')
    if job.status not in ('Queued', 'Running', 'WaitingForUser'):
        raise HTTPException(409, 'Job is already finished.')
    job.cancel_requested = True
    if job.status == 'Queued':
        from services.completion import prepare_completions
        job.status, job.completed_at = 'Cancelled', datetime.now(timezone.utc)
        prepare_completions(session, job)
    return {'message': 'Job cancelled.' if job.status == 'Cancelled' else 'Job cancellation requested.'}


def resume_visible_job(session, job, user):
    from fastapi import HTTPException
    from services.visibility import is_job_visible
    if not job or not is_job_visible(job, user, session):
        raise HTTPException(404, 'Job not found.')
    if job.status != 'WaitingForUser':
        raise HTTPException(409, 'Job is not waiting for user interaction.')
    job.resume_requested = True
    return {'message': 'Job resume requested.'}


def enqueue_scrape(
    session: Session,
    *,
    user: Any,
    script_id: str,
    params: Dict[str, Any],
    query_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Tuple[Job, bool]:
    """
    The authoritative entrypoint to create scrape jobs.
    Called exclusively by the LangGraph enqueue_job node.
    Returns (job, created: bool).
    """
    clean_id = (script_id or "").strip().lower()

    try:
        meta = get_meta(clean_id)
    except (UnknownScraper, Exception) as e:
        raise ScrapeNotAllowed(f"Unknown scraper source: '{script_id}': {e}") from e

    ready, reason = check_ready(clean_id)
    if not ready:
        raise ScraperNotReady(f"Scraper '{clean_id}' is not ready: {reason}")

    validated_params = validate_params(clean_id, params)
    params_dict = validated_params.model_dump()

    user_id = getattr(user, "id", str(user))
    if query_id:
        origin = session.get(Query, query_id)
        if origin:
            from services.sessions import require_active
            require_active(origin.session_id, session)
    dept_id = getattr(user, "department_id", None) or "dept-default"

    params_hash = hashlib.sha256(json.dumps(params_dict, sort_keys=True).encode()).hexdigest()
    if idempotency_key:
        session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'enqueue-key:' + idempotency_key})

    # A transaction lock makes select/reuse/insert atomic across requests/users.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {'key': 'enqueue:' + clean_id + ':' + params_hash})
    # 1. Idempotency check by idempotency_key
    if idempotency_key:
        existing = session.scalar(
            select(Job).where(Job.idempotency_key == idempotency_key)
        )
        if existing:
            if query_id:
                q = session.get(Query, query_id)
                if q:
                    q.job_id = existing.id
                    session.flush()
            return existing, False

    # 2. Check for active identical job (script_id + params_hash in Queued or Running)
    existing_active = session.scalar(
        select(Job)
        .where(Job.script_id == clean_id)
        .where(Job.params_hash == params_hash)
        .where(Job.status.in_(["Queued", "Running", "WaitingForUser"]))
        .order_by(Job.created_at.asc())
    )
    if existing_active:
        if query_id:
            q = session.get(Query, query_id)
            if q:
                q.job_id = existing_active.id
                session.flush()
        return existing_active, False

    from Database.models.source import Source
    src = session.query(Source).filter(Source.code == clean_id).first()
    source_id = src.id if src else None

    limit = validated_params.limit
    job = Job(
        name=f"{meta.name} Scrape",
        type="scrape",
        script_id=clean_id,
        script_name=meta.name,
        source_id=source_id,
        status="Queued",
        progress=0,
        created_by=user_id,
        department_id=dept_id,
        query_id=query_id,
        idempotency_key=idempotency_key,
        params_hash=params_hash,
        total_target=limit,
        parameters=params_dict,
        logs=[],
    )
    session.add(job)
    session.flush()

    if query_id:
        q = session.get(Query, query_id)
        if q:
            q.job_id = job.id
            session.flush()

    return job, True


def job_status_data(session, job):
    from routes.serializers import serialize_job
    from sqlalchemy import and_, or_
    data = serialize_job(job)
    if job.status == 'Queued':
        ahead = session.scalar(select(func.count(Job.id)).where(Job.status == 'Queued', or_(
            Job.created_at < job.created_at, and_(Job.created_at == job.created_at, Job.id < job.id)))) or 0
        running = session.scalar(select(func.count(Job.id)).where(Job.status.in_(['Running', 'WaitingForUser']))) or 0
        data['queuePosition'] = ahead + 1
        data['waitingForOtherScrape'] = bool(running)
        if settings.ENVIRONMENT == 'development' and settings.SELENIUM_MODE == 'local':
            from services.worker_runtime import worker_present
            data['workerAvailable'] = worker_present()
        data['currentStep'] = (f'Waiting for another scrape to finish; queue position {ahead + 1}.' if running else
                               f'Waiting for a worker; queue position {ahead + 1}.')
        data['current_step'] = data['currentStep']
    return data
