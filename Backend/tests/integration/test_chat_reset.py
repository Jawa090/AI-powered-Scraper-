"""Chat clear cancels work, deletes model state and retains saved data without cancellation reports."""
import threading
import uuid
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.job import Job
from Database.models.session import AgentSession
from Database.models.session_event import SessionEvent
from services.sessions import new_session, reset_session
from services.jobs import enqueue_scrape, job_status_data
from services.delivery import delivery_rows
from agents.graph.graph import get_compiled_graph
from scrappers.base import StandardRecord
import worker


def account():
    uid = 'reset-'+uuid.uuid4().hex
    with session_scope() as db:
        user = User(id=uid, username=uid, email=uid+'@example.test', name='Reset test', role='user',
                    auth_source='db', status='Active', department_id='dept-default')
        db.add(user); db.flush()
    return user


def queued(user, sid):
    qid = str(uuid.uuid4())
    with session_scope() as db:
        db.add(Query(id=qid, session_id=sid, user_id=user.id, query_text='1 roofer NYC with both contacts',
            parameters={'slots':dict(record_kind='company', category='reset-'+qid, city='New York', us_state='NY',
                        quantity=1, has_email=True, has_phone=True, source='jwiz')})); db.flush()
        job, _ = enqueue_scrape(db, user=user, script_id='jwiz', params={'limit':1,'keyword':qid,'city':'New York','us_state':'NY'}, query_id=qid)
        return job.id, qid


def test_clear_cancels_queued_job_erases_checkpoint_and_keeps_audit():
    user=account(); sid=new_session(user); jid,qid=queued(user,sid)
    graph=get_compiled_graph()
    config={'configurable':{'thread_id':sid}}
    graph.update_state(config, {'session_id':sid, 'slots':{'quantity':1,'category':'old roofing'}}, as_node='load_context')
    assert graph.get_state(config).values
    result=reset_session(user,sid)
    assert result['sessionId'] != sid and result['clearedSessionIds']==[sid]
    assert not graph.get_state(config).values
    with session_scope() as db:
        assert db.get(Job,jid).status=='Cancelled'
        assert db.get(AgentSession,sid).status=='cleared'
        assert db.get(Query,qid).parameters['chatCleared']
        event=db.scalar(select(SessionEvent).where(SessionEvent.job_id==jid))
        assert event.status=='delivered'
        q=db.get(Query,event.query_id)
        assert q.response['suppressed']
        assert q.served_at is None
    from agents.graph.runner import run_turn
    with pytest.raises(HTTPException) as closed:
        run_turn(user,sid,'approve')
    assert closed.value.status_code==409


def test_clear_running_job_saves_inflight_data_silently_without_model(monkeypatch, caplog):
    caplog.set_level(20)
    user=account(); sid=new_session(user); jid,qid=queued(user,sid)
    with session_scope() as db:
        db.get(Job,jid).status = 'Running'  # The real queue claim sets this before execution.
    ready,release=threading.Event(),threading.Event()
    tag='cancel-'+uuid.uuid4().hex
    def stream(*args, **kwargs):
        yield StandardRecord(source_code='jwiz',record_kind='company',external_id=tag+'1',organization_name=tag+'1')
        ready.set()
        assert release.wait(10)
        yield StandardRecord(source_code='jwiz',record_kind='company',external_id=tag+'2',organization_name=tag+'2')
    monkeypatch.setattr(worker.controller,'run',stream)
    errors=[]
    def execute():
        try: worker.execute_job(jid,'reset-test')
        except Exception as exc: errors.append(exc)
    thread=threading.Thread(target=execute); thread.start()
    assert ready.wait(10)
    try:
        with session_scope() as db:
            assert db.get(Job,jid).records_found==1 and db.get(Job,jid).progress>0
        first_reset=reset_session(user,sid)
        second_reset=reset_session(user,first_reset['sessionId'])
        assert second_reset['clearedSessionIds']==[first_reset['sessionId']]
    finally:
        release.set(); thread.join(10)
    assert not thread.is_alive() and not errors
    with session_scope() as db:
        assert db.get(Job,jid).status=='Cancelled'
        assert db.get(Job,jid).records_found == 2
        event=db.scalar(select(SessionEvent).where(SessionEvent.job_id==jid))
        assert event.status=='delivered'
        q=db.get(Query,event.query_id)
        assert len(delivery_rows(db,q.id))==0
        assert q.parameters['requestFulfilled'] is False and q.parameters['collectionCancelled']
        assert q.response['suppressed'] and q.served_at is None
        from Database.models.message import AgentMessage
        assert db.get(AgentMessage,q.id+':agent') is None
    assert 'recovered_records=0' in caplog.text and 'user/admin report suppressed' in caplog.text


def test_clear_shared_job_detaches_only_cleared_subscriber():
    first,second=account(),account()
    sid1,sid2=new_session(first),new_session(second)
    jid,qid=queued(first,sid1)
    with session_scope() as db:
        db.add(Query(id=str(uuid.uuid4()),session_id=sid2,user_id=second.id,job_id=jid,
                     parameters={'slots':dict(record_kind='company',quantity=1,source='jwiz')}))
    reset_session(first,sid1)
    with session_scope() as db:
        job=db.get(Job,jid)
        assert job.status=='Queued' and not job.cancel_requested
        event=db.scalar(select(SessionEvent).where(SessionEvent.session_id==sid1))
        assert event.status=='delivered'
        assert db.scalar(select(SessionEvent).where(SessionEvent.session_id==sid2)) is None


def test_clear_cannot_reset_another_users_chat_and_queue_reports_wait():
    owner,other=account(),account()
    sid=new_session(owner); jid,_=queued(owner,sid)
    with pytest.raises(HTTPException) as denied:
        reset_session(other,sid)
    assert denied.value.status_code==404
    with session_scope() as db:
        blocker=Job(id=str(uuid.uuid4()),name='Queue blocker',status='Running',parameters={})
        db.add(blocker);db.flush()
        status=job_status_data(db,db.get(Job,jid))
        assert status['queuePosition']>=1 and status['waitingForOtherScrape']
        assert 'another scrape' in status['currentStep']
        blocker.status='Cancelled'


@pytest.mark.parametrize('count', [0, 1])
def test_timeout_persists_dump_and_reports_recovery_even_when_ai_unavailable(monkeypatch, count):
    from services.jobs import ScraperNoDataTimeout
    from agents.llm.chat_model import LLMUnavailable
    import agents.graph.runner as runner
    user=account(); sid=new_session(user); jid,_=queued(user,sid)
    tag='timeout-'+uuid.uuid4().hex
    def stream(*args, **kwargs):
        for index in range(count):
            yield StandardRecord(source_code='jwiz',record_kind='company',external_id=tag,
                                 organization_name=tag)
        raise ScraperNoDataTimeout('Scraper stopped: no records received for 5 minutes.')
    monkeypatch.setattr(worker.controller,'run',stream)
    worker.execute_job(jid,'timeout-test')
    def unavailable(*args, **kwargs):
        raise LLMUnavailable('timeout')
    monkeypatch.setattr(runner,'invoke_llm',unavailable)
    result=runner.run_event_turn(sid,jid)
    assert result['timedOut'] and not result['requestFulfilled']
    assert len(result['records'])==0 and len(result['timeoutOptions']['scrapers'])==4
    assert result['timeoutOptions']['recommendedSource'] is None
    assert 'rerun' in result['reply'] and 'five minutes' in result['reply']
    with session_scope() as db:
        assert db.get(Job,jid).status == ('Partial' if count else 'Failed')
        assert len(delivery_rows(db,result['queryId']))==0
        assert db.get(Query,result['queryId']).served_at is not None
    reset_session(user,sid)
    from fastapi.testclient import TestClient
    from app import app
    from services.auth import create_access_token
    receipt=TestClient(app).get('/api/bot/cleared-recovery/'+sid,
        headers={'Authorization':'Bearer '+create_access_token(user)})
    assert receipt.status_code == 200 and receipt.json()['deliveries']==[]


def test_worker_singleton_lock_releases_and_retry_recommendation_respects_coverage(monkeypatch):
    from services.worker_runtime import local_worker_lock, worker_present
    from services.recovery_options import timeout_options
    assert not worker_present()
    with local_worker_lock() as acquired:
        assert acquired and worker_present()
        with local_worker_lock() as second:
            assert not second
    assert not worker_present()
    monkeypatch.setattr('services.recovery_options.check_ready', lambda _: (True, []))
    options=timeout_options(dict(record_kind='opportunity',category='roofing',city=None,
                                 us_state='NY',quantity=1), 'dasny')
    assert options['recommendedSource']=='nyscr'
    assert not next(row for row in options['scrapers'] if row['id']=='bonfire')['compatible']


def test_legacy_clear_receipts_are_hidden_from_user_and_admin():
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    from app import app
    from Database.models.message import AgentMessage
    from services.auth import create_access_token
    from agents.graph.runner import run_event_turn
    user=account(); sid=new_session(user); jid,_=queued(user,sid)
    reset_session(user,sid)
    with session_scope() as db:
        event=db.scalar(select(SessionEvent).where(SessionEvent.job_id==jid))
        q=db.get(Query,event.query_id)
        event_id=q.id
        # Simulate a receipt created by the earlier implementation.
        q.served_at=datetime.now(timezone.utc)
        q.records_returned=1
        q.response={'reply':'Obsolete cancellation report', 'collectionCancelled':True}
        db.add(AgentMessage(id=q.id+':agent',session_id=sid,sender='agent',role='agent',
            text='Obsolete cancellation report',message_metadata={'collectionCancelled':True,'queryId':q.id}))
        admin_token=create_access_token(db.get(User,'usr-env-admin'))
    client=TestClient(app)
    headers={'Authorization':'Bearer '+admin_token}
    assert client.get('/api/admin/deliveries',params={'user_id':user.id},headers=headers).json()['groups'][0]['total']==0
    assert event_id not in client.get('/api/admin/deliveries/export.csv',headers=headers).text
    requests=client.get('/api/admin/requests',params={'user_id':user.id},headers=headers).json()
    assert event_id not in str(requests)
    assert client.get('/api/admin/requests/'+event_id,headers=headers).status_code==404
    user_headers={'Authorization':'Bearer '+create_access_token(user)}
    assert client.get('/api/bot/sessions/'+sid+'/messages',headers=user_headers).json()['messages']==[]
    assert client.get('/api/bot/cleared-recovery/'+sid,headers=user_headers).json()['deliveries']==[]
    assert run_event_turn(sid,jid)['suppressed']

