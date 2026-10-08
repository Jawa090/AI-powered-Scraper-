"""
Backend/tests/integration/test_worker.py
────────────────────────────────────────
Integration tests for PostgreSQL job queue worker process (Phase P7.2-P7.6).
Verifies:
- Worker claims and executes jobs using FOR UPDATE SKIP LOCKED
- Datasets, ScrapeRuns, Leads, QueryResults, and event messages are written
- Multiple queries served by a single deduplicated job
- Cancellation requests respected and mapped to 'Cancelled'
- Reaper touches only stale Running/WaitingForUser jobs and never Queued jobs
- CAPTCHA wait_for_user transitions to WaitingForUser, resumes on resume_requested, and fails on timeout
"""

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
import pytest

from Database.controller import session_scope
from Database.models.dataset import Dataset
from Database.models.job import Job
from Database.models.message import AgentMessage
from Database.models.query import Query
from Database.models.query_result import QueryResult
from Database.models.session_event import SessionEvent
from Database.models.scrape_run import ScrapeRun
from Database.models.session import AgentSession
from services.jobs import (
    JobCancelled,
    UserWaitTimeout,
    enqueue_scrape,
)
from worker import (
    JobContext,
    claim_job,
    execute_job,
    reap_stale_jobs,
    run_worker_loop,
)
from settings import settings


@pytest.fixture(autouse=True)
def ensure_fixture_mode(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPER_MODE", "fixture")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    with session_scope() as session:
        assert 'test' in session.bind.url.database.lower()
        session.query(SessionEvent).delete()
        session.query(QueryResult).delete()
        session.query(Query).delete()
        session.query(ScrapeRun).delete()
        session.query(Dataset).delete()
        session.query(AgentMessage).delete()
        session.query(AgentSession).delete()
        session.query(Job).delete()
        session.commit()


from Database.models.user import User


def _create_test_user(session, name="Test Worker User") -> User:
    u_id = f"usr-{uuid.uuid4().hex[:8]}"
    u = User(
        id=u_id,
        username=u_id,
        name=name,
        email=f"{u_id}@example.com",
        role="user",
        department_id="dept-default",
        auth_source="db",
        status="Active",
    )
    session.add(u)
    session.flush()
    return u


def test_worker_executes_job_and_ingests():
    """
    P7.6 Test:
    enqueue -> python -m worker --once -> job Completed, dataset Completed,
    query_results rows written, event message created.
    """
    session_id = f"sess-{uuid.uuid4().hex[:8]}"

    with session_scope() as session:
        user = _create_test_user(session, "Worker User 1")
        agent_sess = AgentSession(
            id=session_id,
            agent_id="agent-master",
            department_id="dept-default",
            user_id=user.id,
            title="Test Session",
        )
        session.add(agent_sess)
        session.flush()

        query_id = f"qry-{uuid.uuid4().hex[:8]}"
        q = Query(
            id=query_id,
            session_id=session_id,
            user_id=user.id,
            query_text="Find bids in Dallas",
            parameters={"slots": {"record_kind": "opportunity", "quantity": 2, "source": "bonfire"}},
        )
        session.add(q)
        session.flush()

        job, created = enqueue_scrape(
            session,
            user=user,
            script_id="bonfire",
            params={"limit": 2},
            query_id=query_id,
        )
        assert created is True
        assert job.status == "Queued"
        job_id = job.id

    # Run worker once
    run_worker_loop(once=True)

    # Verify execution outcome
    with session_scope() as session:
        j = session.get(Job, job_id)
        assert j.status == "Completed"
        assert j.records_found >= 1
        assert j.verified_count >= 1
        assert j.dataset_id is not None
        assert j.completed_at is not None

        # Dataset completed
        ds = session.get(Dataset, j.dataset_id)
        assert ds is not None
        assert ds.status == "Completed"
        assert ds.records_count == j.records_found

        # ScrapeRun completed
        sr = session.query(ScrapeRun).filter(ScrapeRun.job_id == j.id).first()
        assert sr is not None
        assert sr.status == "Completed"

        # Collection does not overwrite the original response. A durable private
        # event owns the selected rows until the completion is actually delivered.
        qry = session.get(Query, query_id)
        assert qry.served_at is None
        event = session.query(SessionEvent).filter_by(job_id=job_id).one()
        assert event.status == 'pending'
        completion = session.get(Query, event.query_id)
        assert completion.records_returned == 2
        assert completion.served_at is None
        assert session.query(QueryResult).filter_by(query_id=event.query_id).count() == 2



def test_two_queries_served_by_one_job():
    """
    P7.6 Test:
    identical parameters from two users -> one job, and BOTH queries are served.
    """
    sess1_id = f"sess-{uuid.uuid4().hex[:8]}"
    sess2_id = f"sess-{uuid.uuid4().hex[:8]}"

    with session_scope() as session:
        user1 = _create_test_user(session, "User 1")
        user2 = _create_test_user(session, "User 2")
        session.add_all([
            AgentSession(
                id=sess1_id,
                agent_id="agent-master",
                department_id="dept-default",
                user_id=user1.id,
                title="User 1 Session",
            ),
            AgentSession(
                id=sess2_id,
                agent_id="agent-master",
                department_id="dept-default",
                user_id=user2.id,
                title="User 2 Session",
            ),
        ])
        session.flush()

        q1 = Query(
            id=f"qry-{uuid.uuid4().hex[:8]}",
            session_id=sess1_id,
            user_id=user1.id,
            parameters={"slots": {"record_kind": "opportunity", "quantity": 2, "source": "bonfire"}},
        )
        q2 = Query(
            id=f"qry-{uuid.uuid4().hex[:8]}",
            session_id=sess2_id,
            user_id=user2.id,
            parameters={"slots": {"record_kind": "opportunity", "quantity": 2, "source": "bonfire"}},
        )
        session.add_all([q1, q2])
        session.flush()

        params = {"limit": 2, "keyword": "services"}
        job1, created1 = enqueue_scrape(session, user=user1, script_id="bonfire", params=params, query_id=q1.id)
        job2, created2 = enqueue_scrape(session, user=user2, script_id="bonfire", params=params, query_id=q2.id)

        assert created1 is True
        assert created2 is False
        assert job1.id == job2.id
        job_id = job1.id
        q1_id = q1.id
        q2_id = q2.id

    # Run worker once
    run_worker_loop(once=True)

    with session_scope() as session:
        j = session.get(Job, job_id)
        assert j.status == "Completed"

        events = session.query(SessionEvent).filter_by(job_id=job_id).all()
        assert len(events) == 2
        assert all(e.status == 'pending' for e in events)
        assert {session.get(Query, e.query_id).user_id for e in events} == {user1.id, user2.id}
        for event in events:
            assert session.query(QueryResult).filter_by(query_id=event.query_id).count() == 2
        assert session.get(Query, q1_id).served_at is None
        assert session.get(Query, q2_id).served_at is None



def test_job_cancellation():
    """
    P7.6 Test:
    Job cancelled -> Cancelled status on job and dataset.
    """
    with session_scope() as session:
        user = _create_test_user(session, "Cancel User")
        job, created = enqueue_scrape(
            session,
            user=user,
            script_id="bonfire",
            params={"limit": 5},
        )
        job.cancel_requested = True
        session.commit()
        job_id = job.id

    run_worker_loop(once=True)

    with session_scope() as session:
        j = session.get(Job, job_id)
        assert j.status == "Cancelled"
        if j.dataset_id:
            ds = session.get(Dataset, j.dataset_id)
            assert ds.status == "Cancelled"


def test_reaper_only_touches_stale_running_jobs():
    """
    P7.4 / P7.6 Test:
    The reaper touches only stale Running / WaitingForUser jobs and never Queued.
    """
    stale_running_id = f"job-stale-{uuid.uuid4().hex[:8]}"
    queued_id = f"job-queued-{uuid.uuid4().hex[:8]}"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)

    with session_scope() as session:
        ds = Dataset(id=f"d-{stale_running_id}", name="Stale DS", status="Running")
        session.add(ds)
        session.flush()

        stale_job = Job(
            id=stale_running_id,
            name="Stale Running Job",
            script_id="bonfire",
            status="Running",
            dataset_id=ds.id,
            heartbeat_at=old_time,
            parameters={},
            logs=[],
        )
        queued_job = Job(
            id=queued_id,
            name="Queued Job",
            script_id="bonfire",
            status="Queued",
            created_at=old_time,
            parameters={},
            logs=[],
        )
        session.add_all([stale_job, queued_job])
        session.commit()

    with session_scope() as session:
        reaped_count = reap_stale_jobs(session)
        assert reaped_count >= 1

    with session_scope() as session:
        sj = session.get(Job, stale_running_id)
        assert sj.status == "Failed"
        assert "heartbeat timeout" in sj.error_message
        sds = session.get(Dataset, f"d-{stale_running_id}")
        assert sds.status == "Failed"

        # Queued job remains Queued
        qj = session.get(Job, queued_id)
        assert qj.status == "Queued"


def test_captcha_waiting_and_resume():
    """
    P7.3 / P7.6 Test:
    wait_for_user sets status='WaitingForUser', emits event,
    and resumes to Running when resume_requested=True.
    """
    job_id = f"job-cap-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        job = Job(
            id=job_id,
            name="Captcha Test Job",
            script_id="ny",
            status="Running",
            parameters={},
            logs=[],
        )
        session.add(job)
        session.commit()

    ctx = JobContext(job_id=job_id, worker_id="test-worker")

    # Resume the job in a background thread after 0.5s
    def _resume_later():
        time.sleep(0.5)
        with session_scope() as session:
            j = session.get(Job, job_id)
            if j:
                j.resume_requested = True
                session.commit()

    t = threading.Thread(target=_resume_later, daemon=True)
    t.start()

    resumed = ctx.wait_for_user("reCAPTCHA challenge")
    assert resumed is True

    with session_scope() as session:
        j = session.get(Job, job_id)
        assert j.status == "Running"
        assert j.waiting_for is None


def test_captcha_waiting_timeout(monkeypatch):
    """
    P7.3 / P7.6 Test:
    User wait timeout raises UserWaitTimeout after CAPTCHA_WAIT_SECONDS.
    """
    job_id = f"job-to-{uuid.uuid4().hex[:8]}"
    with session_scope() as session:
        job = Job(
            id=job_id,
            name="Timeout Test Job",
            script_id="ny",
            status="Running",
            parameters={},
            logs=[],
        )
        session.add(job)
        session.commit()

    # Set very short timeout for testing
    monkeypatch.setattr(settings, "CAPTCHA_WAIT_SECONDS", 1)
    ctx = JobContext(job_id=job_id, worker_id="test-worker")

    with pytest.raises(UserWaitTimeout):
        ctx.wait_for_user("captcha test timeout")


def test_worker_continues_past_seen_missing_email_and_expired_records(monkeypatch):
    """Shared collection must fulfill each user's remaining eligible records."""
    from scrappers.base import StandardRecord
    from services.ingest import upsert_leads
    from services.delivery import record_delivery, delivery_rows
    from routes.serializers import serialize_lead
    from Database.models.lead import Lead
    import worker

    tag = 'worker-filter-' + uuid.uuid4().hex
    def raw(index, **overrides):
        values = dict(source_code='bonfire', record_kind='opportunity',
            external_id=f'{tag}-{index}', title=f'{tag} bid {index}', category=tag,
            organization_name='City of Dallas', city='Dallas', us_state='TX',
            email=f'{tag}-{index}@example.test', due_at=datetime.now(timezone.utc) + timedelta(days=10))
        values.update(overrides)
        return StandardRecord(**values)
    records = [raw(0), raw(1), raw(2, email=None),
        raw(3, due_at=datetime.now(timezone.utc) - timedelta(days=1)), raw(4), raw(5)]
    with session_scope() as db:
        users = [_create_test_user(db) for _ in range(2)]
        sessions = [AgentSession(id=str(uuid.uuid4()), agent_id='agent-master',
            department_id='dept-default', user_id=user.id) for user in users]
        db.add_all(sessions); db.flush()
        saved = upsert_leads(db, records[:2])
        seen = Query(id=str(uuid.uuid4()), session_id=sessions[0].id, user_id=users[0].id, parameters={})
        db.add(seen); db.flush()
        record_delivery(db, seen, [serialize_lead(db.get(Lead, saved.lead_ids[0]))])
        slots = dict(category=tag, source='bonfire', record_kind='opportunity', quantity=2,
            city='Dallas', us_state='TX', new_only=True, has_email=True)
        origins = [Query(id=str(uuid.uuid4()), session_id=s.id, user_id=u.id, parameters={'slots': slots})
            for s, u in zip(sessions, users)]
        db.add_all(origins); db.flush()
        record_delivery(db, origins[0], [serialize_lead(db.get(Lead, saved.lead_ids[1]))])
        record_delivery(db, origins[1], [])
        job, _ = enqueue_scrape(db, user=users[0], script_id='bonfire',
            params={'limit': 1}, query_id=origins[0].id)
        origins[1].job_id = job.id
        job_id = job.id
        origin_ids = [q.id for q in origins]
    consumed = []
    closed = []
    def stream(source, params, **kwargs):
        assert params['limit'] == worker.controller.get_meta(source).max_limit
        try:
            for item in records:
                consumed.append(item.external_id)
                yield item
        finally:
            closed.append(True)
    monkeypatch.setattr(worker.controller, 'run', stream)
    execute_job(job_id, 'test-worker')
    assert consumed == [r.external_id for r in records]
    assert closed == [True]
    with session_scope() as db:
        assert db.get(Job, job_id).status == 'Completed'
        events = db.query(Query).filter(Query.job_id == job_id, Query.status == 'event_pending').all()
        assert len(events) == 2
        for event in events:
            rows = delivery_rows(db, event.id)
            if event.parameters['originatingQueryId'] == origin_ids[0]:
                assert len(rows) == 1
                assert rows[0]['title'] in {records[4].title, records[5].title}
                assert event.parameters['initialRecordsDelivered'] == 1
            else:
                assert len(rows) == 2
                assert all(row['email'] for row in rows)
        assert db.get(Query, origin_ids[0]).records_returned == 1


def test_worker_marks_shortfall_partial_when_only_seen_records_exist(monkeypatch):
    from scrappers.base import StandardRecord
    from services.ingest import upsert_leads
    from services.delivery import record_delivery, delivery_rows
    from routes.serializers import serialize_lead
    from Database.models.lead import Lead
    import worker
    tag = 'worker-seen-' + uuid.uuid4().hex
    raw = StandardRecord(source_code='jwiz', record_kind='company', external_id=tag,
        organization_name=tag, category=tag, city='New York', us_state='NY')
    with session_scope() as db:
        user = _create_test_user(db)
        sess = AgentSession(id=str(uuid.uuid4()), agent_id='agent-master',
            department_id='dept-default', user_id=user.id)
        db.add(sess); db.flush()
        lead_id = upsert_leads(db, [raw]).lead_ids[0]
        seen = Query(id=str(uuid.uuid4()), session_id=sess.id, user_id=user.id, parameters={})
        db.add(seen); db.flush()
        record_delivery(db, seen, [serialize_lead(db.get(Lead, lead_id))])
        origin = Query(id=str(uuid.uuid4()), session_id=sess.id, user_id=user.id,
            parameters={'slots': {'category': tag, 'quantity': 1, 'source': 'jwiz', 'new_only': True}})
        db.add(origin); db.flush()
        job, _ = enqueue_scrape(db, user=user, script_id='jwiz', params={'limit': 1, 'us_state': 'NY'}, query_id=origin.id)
        job_id = job.id
    monkeypatch.setattr(worker.controller, 'run', lambda *a, **kw: iter([raw]))
    execute_job(job_id, 'test-worker')
    with session_scope() as db:
        assert db.get(Job, job_id).status == 'Partial'
        event = db.query(Query).filter_by(job_id=job_id, status='event_pending').one()
        assert [row['id'] for row in delivery_rows(db, event.id)] == [lead_id]
        assert event.parameters['requestFulfilled'] is False
        assert event.parameters['matchingRecordsDelivered'] == 0
        assert event.parameters['deliveryKind'] == 'recovered'
