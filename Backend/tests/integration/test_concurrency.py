"""Actual PostgreSQL races for identity, queue reuse and active sessions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import uuid
from sqlalchemy import select, func
from Database.controller import session_scope
from Database.models.user import User
from Database.models.job import Job
from Database.models.query import Query
from Database.models.session import AgentSession
from Database.models.lead import Lead
from services.ingest import upsert_leads
from services.jobs import enqueue_scrape, cancel_visible_job
from services.sessions import new_session
from services.visibility import is_job_visible
from worker import claim_job
from fastapi import HTTPException
import pytest


def account():
    uid='race-'+uuid.uuid4().hex
    with session_scope() as db:
        row=User(id=uid,username=uid,email=uid+'@example.test',name='Concurrency test',role='user',
            status='Active',auth_source='db',department_id='dept-default')
        db.add(row); db.flush()
    return row


def test_concurrent_ingestion_keeps_one_identity():
    tag=uuid.uuid4().hex
    record={'source_code':'jwiz','record_kind':'company','external_id':tag,
        'organization_name':'Concurrency roofing '+tag,'category':'Roofing','city':'New York','us_state':'NY','email':tag+'@example.test'}
    def ingest(_):
        with session_scope() as db: return upsert_leads(db,[record])
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(ingest,range(2)))
    assert all(result.failed==0 for result in results)
    assert results[0].lead_ids==results[1].lead_ids
    assert sum(result.inserted for result in results)==1
    assert sum(result.unchanged for result in results)==1


def test_simultaneous_requests_reuse_job_and_keep_subscriber_permissions():
    users=[account(),account()]; ids=[]; tag=uuid.uuid4().hex
    with session_scope() as db:
        for user in users:
            sid='race-session-'+uuid.uuid4().hex; qid='race-query-'+uuid.uuid4().hex
            db.add(AgentSession(id=sid,user_id=user.id,agent_id='agent-master',department_id='dept-default'))
            db.flush(); db.add(Query(id=qid,user_id=user.id,session_id=sid,parameters={})); ids.append(qid)
    def queue(index):
        with session_scope() as db:
            job,created=enqueue_scrape(db,user=users[index],script_id='jwiz',params={'keyword':'roofing '+tag,'limit':2,'us_state':'NY'},query_id=ids[index])
            return job.id,created
    with ThreadPoolExecutor(max_workers=2) as pool: jobs=list(pool.map(queue,range(2)))
    assert jobs[0][0]==jobs[1][0] and sum(created for _,created in jobs)==1
    with session_scope() as db:
        job=db.get(Job,jobs[0][0])
        assert all(is_job_visible(job,user,db) for user in users)
        assert all(db.get(Query,qid).job_id==job.id for qid in ids)
        for user in users:
            with pytest.raises(HTTPException) as error: cancel_visible_job(db,job,user)
            assert error.value.status_code==409


def test_two_workers_claim_distinct_jobs():
    ids=['race-claim-'+uuid.uuid4().hex for _ in range(2)]
    with session_scope() as db:
        for jid in ids: db.add(Job(id=jid,name='Concurrency claim',status='Queued',parameters={},logs=[],created_at=datetime(1970,1,1,tzinfo=timezone.utc)))
    def claim(index):
        with session_scope() as db: return claim_job(db,'concurrent-worker-'+str(index))
    with ThreadPoolExecutor(max_workers=2) as pool: claimed=list(pool.map(claim,range(2)))
    assert set(claimed)==set(ids)
    with session_scope() as db:
        for jid in ids: db.get(Job,jid).status='Cancelled'


def test_concurrent_new_chat_preserves_both_sessions_and_one_active():
    user=account()
    with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(lambda _: new_session(user),range(2)))
    with session_scope() as db:
        sessions=db.scalars(select(AgentSession).where(AgentSession.user_id==user.id)).all()
        assert {row.id for row in sessions}==set(ids)
        assert sum(row.status=='active' for row in sessions)==1
