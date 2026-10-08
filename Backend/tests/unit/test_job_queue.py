"""
Backend/tests/unit/test_job_queue.py
───────────────────────────────────
Unit tests for Postgres job queue service (P7.1) and status mapping (P7.5).
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest

from Database.controller import session_scope
from Database.models.job import Job
from Database.models.user import User
from Database.models.query import Query
from services.jobs import (
    InvalidScrapeParams,
    ScrapeNotAllowed,
    UserWaitTimeout,
    enqueue_scrape,
)
from worker import compute_job_status
from settings import settings


def test_job_status_mapping():
    """
    P7.5 Job status mapping table verification:
    | Outcome | Status |
    | all records saved | Completed |
    | some failed or skipped | Partial |
    | scraper error before any record | Failed |
    | cancelled | Cancelled |
    | CAPTCHA timeout | Failed |
    """
    # 1. All records saved
    assert compute_job_status(
        total_found=20, inserted=15, updated=5, failed=0, skipped=0
    ) == "Completed"

    # 2. Some failed or skipped
    assert compute_job_status(
        total_found=20, inserted=10, updated=5, failed=3, skipped=2
    ) == "Partial"

    # 3. Scraper error before any record
    assert compute_job_status(
        total_found=0, inserted=0, updated=0, failed=0, skipped=0, scraper_error=True
    ) == "Failed"

    # 4. Scraper error after some records saved
    assert compute_job_status(
        total_found=10, inserted=5, updated=2, failed=0, skipped=0, scraper_error=True
    ) == "Partial"

    # 5. Cancelled
    assert compute_job_status(
        total_found=10, inserted=5, updated=2, failed=0, skipped=0, cancelled=True
    ) == "Cancelled"

    # 6. CAPTCHA timeout
    assert compute_job_status(
        total_found=5, inserted=2, updated=0, failed=0, skipped=0, captcha_timeout=True
    ) == "Failed"


def test_enqueue_scrape_validates_unknown_scraper(db_session, make_user):
    user = make_user()
    with pytest.raises(ScrapeNotAllowed):
        enqueue_scrape(
            db_session,
            user=user,
            script_id="unknown_unregistered_scraper",
            params={"limit": 10},
        )


def test_enqueue_scrape_validates_params(db_session, make_user):
    user = make_user()
    # Limit out of bounds (< 1)
    with pytest.raises(InvalidScrapeParams):
        enqueue_scrape(
            db_session,
            user=user,
            script_id="bonfire",
            params={"limit": 0},
        )

    # Limit out of bounds is now uncapped
    job, created = enqueue_scrape(
        db_session,
        user=user,
        script_id="bonfire",
        params={"limit": 500},
    )
    assert job.parameters["limit"] == 500


def test_enqueue_has_no_hourly_limit(db_session, make_user):
    user = make_user()
    for i in range(12):
        db_session.add(Job(name='Prior job', script_id='bonfire', status='Completed', created_by=user.id))
    db_session.flush()
    job, created = enqueue_scrape(db_session, user=user, script_id='bonfire', params={'limit': 5})
    assert job.status == 'Queued'


def test_enqueue_scrape_idempotency_key(db_session, make_user):
    user = make_user()
    idem_key = f"idem-{uuid.uuid4().hex}"

    job1, created1 = enqueue_scrape(
        db_session,
        user=user,
        script_id="bonfire",
        params={"limit": 10, "keyword": "safety"},
        idempotency_key=idem_key,
    )
    db_session.commit()
    assert created1 is True
    assert job1.status == "Queued"

    # Second enqueue with same idempotency_key returns existing job
    job2, created2 = enqueue_scrape(
        db_session,
        user=user,
        script_id="bonfire",
        params={"limit": 10, "keyword": "safety"},
        idempotency_key=idem_key,
    )
    assert created2 is False
    assert job2.id == job1.id


def test_enqueue_scrape_identical_parameters_dedup(db_session, make_user):
    user1 = make_user()
    user2 = make_user()

    # Create queries for both users
    q1 = Query(id=f"q1-{uuid.uuid4().hex[:6]}", user_id=user1.id, parameters={})
    q2 = Query(id=f"q2-{uuid.uuid4().hex[:6]}", user_id=user2.id, parameters={})
    db_session.add_all([q1, q2])
    db_session.commit()

    params = {"limit": 15, "keyword": "water"}

    job1, created1 = enqueue_scrape(
        db_session,
        user=user1,
        script_id="bonfire",
        params=params,
        query_id=q1.id,
    )
    db_session.commit()
    assert created1 is True
    assert q1.job_id == job1.id

    # User 2 enqueues with identical parameters
    job2, created2 = enqueue_scrape(
        db_session,
        user=user2,
        script_id="bonfire",
        params=params,
        query_id=q2.id,
    )
    db_session.commit()
    assert created2 is False
    assert job2.id == job1.id
    assert q2.job_id == job1.id
