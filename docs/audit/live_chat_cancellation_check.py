"""Cancel an actual isolated JWiz scrape after committed data, in the test DB."""
import json
import threading
import time
import uuid
from live_recovery_check import ROOT, settings, session_scope, User, Query, Job, SessionEvent
from live_recovery_check import new_session, enqueue_scrape, delivery_rows, create_access_token, TestClient, app, worker
from services.sessions import reset_session
from agents.graph.graph import get_compiled_graph


def main():
    uid = 'live-clear-' + uuid.uuid4().hex
    report = {'realSource': True, 'isolatedDatabase': True}
    with session_scope() as db:
        user = User(id=uid, username=uid, email=uid+'@example.test', name='Cancellation audit',
                    role='user', status='Active', auth_source='db', department_id='dept-default')
        db.add(user); db.flush()
    sid, qid = new_session(user), str(uuid.uuid4())
    with session_scope() as db:
        db.add(Query(id=qid, user_id=uid, session_id=sid, parameters={'slots': dict(record_kind='company',
            category='general contractor', city='New York', us_state='NY', quantity=1,
            has_email=True, has_phone=True, source='jwiz')})); db.flush()
        job, _ = enqueue_scrape(db, user=user, script_id='jwiz', query_id=qid,
            params=dict(limit=1, keyword='general contractor', city='New York', us_state='NY'))
        jid = job.id
        job.status = 'Running'
    errors = []
    def execute():
        try:
            worker.execute_job(jid, 'live-clear-audit')
        except Exception as exc:
            errors.append(type(exc).__name__)
    thread = threading.Thread(target=execute)
    thread.start()
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            with session_scope() as db:
                job = db.get(Job, jid)
                if job.records_found:
                    assert job.status == 'Running', 'Source finished before cancellation could be tested'
                    break
            time.sleep(.05)
        else:
            raise RuntimeError('No committed live record within the bounded check')
        started = time.monotonic()
        reset = reset_session(user, sid)
        thread.join(15)
        assert not thread.is_alive() and not errors
        with session_scope() as db:
            job = db.get(Job, jid)
            assert job.status == 'Cancelled'
            event = db.query(SessionEvent).filter_by(job_id=jid).one()
            query = db.get(Query, event.query_id)
            rows = delivery_rows(db, query.id)
            assert rows and len(rows) == job.verified_count
            assert query.response['suppressed'] and query.served_at is None
            assert query.parameters['requestFulfilled'] is False
            token = create_access_token(db.get(User, 'usr-env-admin'))
        assert not get_compiled_graph().get_state({'configurable': {'thread_id': sid}}).values
        client = TestClient(app)
        receipt = client.get('/api/bot/cleared-recovery/'+sid,
            headers={'Authorization': 'Bearer '+create_access_token(user)}).json()
        assert not receipt['pending'] and receipt['deliveries'] == []
        admin = client.get('/api/admin/deliveries', params={'user_id': uid},
            headers={'Authorization': 'Bearer '+token}).json()
        assert admin['groups'][0]['deliveries'] == []
        report.update(passed=True, jobId=jid, status='Cancelled', recovered=len(rows),
                      stopSeconds=round(time.monotonic()-started, 2), userAndAdminReportsSuppressed=True,
                      newSession=reset['sessionId'], records=rows)
    except Exception as exc:
        reset_session(user)
        thread.join(15)
        report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:300])
    (ROOT/'docs/audit/live_chat_cancellation_verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'records'}), flush=True)
    if not report.get('passed'):
        raise SystemExit(1)


if __name__ == '__main__':
    from agents.graph.checkpointer import setup_checkpointer
    setup_checkpointer()
    main()
