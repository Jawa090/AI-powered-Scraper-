"""Bounded live JWiz recovery check: actual source and provider, isolated DB."""
import json
import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name = json.loads((ROOT / 'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL = make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL = make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
settings.SCRAPER_MODE = 'live'
settings.LLM_TIMEOUT_S = 30
settings.LLM_MAX_RETRIES = 0
from Database.controller import session_scope
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.query import Query
from Database.models.job import Job
from Database.models.dataset import DatasetRecord
from Database.models.session_event import SessionEvent
from services.jobs import enqueue_scrape
from services.auth import create_access_token
from services.sessions import new_session
from services.delivery import delivery_rows, search_request, record_delivery
from agents.graph.runner import run_event_turn
from scrappers.jwiz import JWizScraper
from fastapi.testclient import TestClient
from app import app
import worker
# This process alone uses a five-record audit budget, instead of the normal cap of 100.
JWizScraper.meta = JWizScraper.meta.model_copy(update={'max_limit': 5})
if __name__ == '__main__':
    from agents.graph.checkpointer import setup_checkpointer
    setup_checkpointer()
    uid = 'live-recovery-' + uuid.uuid4().hex
    slots = dict(record_kind='company', category='general contractor', city='New York', us_state='NY',
                 quantity=1, has_email=True, has_phone=True, source='jwiz', new_only=True)
    report = dict(realSource=True, realProvider=True, isolatedDatabase=True, collectionBudget=5, checks=[])
    try:
        with session_scope() as db:
            user = User(id=uid, username=uid, email=uid+'@example.test', name='Live recovery audit',
                        role='user', status='Active', auth_source='db', department_id='dept-default')
            db.add(user); db.flush()
            # The full suite leaves matching fixture records in this disposable DB.
            # Treat those as previously received by this audit account, so they cannot
            # satisfy this live new-only request before the website is checked.
            seen = Query(id=str(uuid.uuid4()), user_id=uid, parameters={'slots': {**slots, 'quantity': 1000, 'new_only': False}})
            db.add(seen); db.flush()
            preexisting, _ = search_request(db, seen)
            record_delivery(db, seen, preexisting)
            report['preexistingAuditMatchesExcluded'] = len(preexisting)
        previous_ids = None
        for index in range(2):
            sid, qid = new_session(user), str(uuid.uuid4())
            with session_scope() as db:
                db.add(Query(id=qid, user_id=uid, session_id=sid, query_text='1 general contractor in New York NY with both email and phone',
                             parameters={'slots': slots})); db.flush()
                job, _ = enqueue_scrape(db, user=user, script_id='jwiz', query_id=qid,
                                       params=dict(limit=1, keyword='general contractor', city='New York', us_state='NY'))
                jid = job.id
            worker.execute_job(jid, 'live-recovery-audit')
            with session_scope() as db:
                job = db.get(Job, jid)
                ids = {r.lead_id for r in db.query(DatasetRecord).filter_by(dataset_id=job.dataset_id)}
                assert len(ids) == 5, f'Expected five recovered rows; saved {len(ids)}'
                event = db.query(SessionEvent).filter_by(job_id=jid).one()
                records = delivery_rows(db, event.query_id)
                params = db.get(Query, event.query_id).parameters
                assert params['requestFulfilled'] is False and params['matchingRecordsDelivered'] == 0
                assert len(records) == 5 and all(row.get('scrapedData') is not None for row in records)
                if previous_ids is not None:
                    assert ids == previous_ids, 'Repeat run introduced duplicate source identities'
                previous_ids = ids
            completion = run_event_turn(sid, jid)
            assert completion['deliveryKind'] == 'recovered' and completion['requestTotalDelivered'] == 0
            assert len(completion['records']) == 5 and completion['showAllDetails']
            with session_scope() as db:
                token = create_access_token(db.get(User, 'usr-env-admin'))
            response = TestClient(app).get('/api/admin/deliveries', params={'user_id': uid},
                                          headers={'Authorization': 'Bearer ' + token})
            assert response.status_code == 200
            delivery = next(d for d in response.json()['groups'][0]['deliveries'] if d['queryId'] == completion['queryId'])
            assert delivery['records'] == completion['records'] and delivery['requestFulfilled'] is False
            assert delivery['understoodRequest'] == slots
            report['checks'].append(dict(jobId=jid, queryId=completion['queryId'], status=completion['status'],
                stored=5, matches=0, displayed=5, duplicateRun=index==1, reply=completion['reply'], records=completion['records'],
                adminEqualsUser=True))
            print(json.dumps(dict(run=index+1, saved=5, matching=0, recoveredDisplayed=5, passed=True)), flush=True)
        report['passed'] = True
    except Exception as exc:
        report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:300])
    (ROOT / 'docs/audit/live_recovery_verification.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print(json.dumps(dict(passed=report.get('passed'), error=report.get('error'))), flush=True)
    if not report.get('passed'):
        raise SystemExit(1)
