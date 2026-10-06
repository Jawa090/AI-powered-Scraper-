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

from sqlalchemy import func, select
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


class ScrapeRateLimited(ScraperException):
    """Raised when the user exceeds the SCRAPES_PER_HOUR threshold."""
    pass


class UserWaitTimeout(ScraperException):
    """Raised when a job waiting for user interaction times out."""
    pass


class WorkerShutdown(ScraperException):
    """Raised when worker receives SIGINT/SIGTERM during job execution."""
    pass


def enforce_scrape_limit(session: Session, user: Any) -> None:
    """Enforce SCRAPES_PER_HOUR rate limit per user."""
    user_id = getattr(user, "id", str(user))
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = (
        select(func.count(Job.id))
        .where(Job.created_by == user_id)
        .where(Job.created_at >= one_hour_ago)
    )
    count = session.scalar(stmt) or 0
    max_scrapes = getattr(settings, "SCRAPES_PER_HOUR", 10)
    if count >= max_scrapes:
        raise ScrapeRateLimited(
            f"User has exceeded the limit of {max_scrapes} scrapes per hour (current: {count})"
        )


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

    enforce_scrape_limit(session, user)

    user_id = getattr(user, "id", str(user))
    dept_id = getattr(user, "department_id", None) or "dept-default"

    params_hash = hashlib.sha256(json.dumps(params_dict, sort_keys=True).encode()).hexdigest()

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
