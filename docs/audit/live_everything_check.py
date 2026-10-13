"""Real-provider contextual everything checks with controlled isolated DB records."""
import json
import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Backend'), str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name = json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL = make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL = make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
settings.LLM_TIMEOUT_S = 25
settings.LLM_MAX_RETRIES = 0
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from services.ingest import upsert_leads
from services.sessions import new_session
from agents.graph.checkpointer import setup_checkpointer
from agents.graph.runner import run_turn
setup_checkpointer()
uid = 'everything-check-' + uuid.uuid4().hex
category = 'general contractor audit' + uuid.uuid4().hex
with session_scope() as db:
    user = User(id=uid, username=uid, email=uid+'@example.test', name='Everything audit',
                role='user', status='Active', department_id='dept-default', auth_source='db')
    db.add(user); db.flush()
    saved = upsert_leads(db, [dict(source_code='jwiz', record_kind='company', external_id=uid,
        organization_name='Everything audit contractor', category=category, city='New York', us_state='NY',
        email=uid+'@example.test', phone='+12125550101', website='https://details.example.test',
        source_url='https://example.test/'+uid, notes='Controlled full-record verification')])
sid = new_session(user)
report = dict(realProvider=True, isolatedDatabase=True, controlledRecord=True, checks=[])
try:
    initial = run_turn(user, sid, f'Get 1 contractor company, exact trade/category "{category}", city New York, state NY.', uuid.uuid4().hex)
    assert initial['missingRequirements'] and not initial['records']
    for text in ['everything', 'get me everything about it in the db', 'show me all his information',
                 'Give me the complete profile for the contractor you just showed me, including every available contact channel']:
        response = run_turn(user, sid, text, uuid.uuid4().hex)
        with session_scope() as db:
            query = db.get(Query, response['queryId'])
            slots = query.parameters['slots']
        assert slots['has_email'] and slots['has_phone'] and response['showAllDetails']
        assert len(response['records']) == 1 and response['records'][0]['id'] == saved.lead_ids[0]
        assert response['records'][0]['website'] == 'https://details.example.test'
        assert response['records'][0]['email'] and response['records'][0]['phone']
        assert not response.get('pendingAction') and not response.get('jobId')
        if text != 'everything':
            assert slots['detail_record_ids'] == saved.lead_ids
        report['checks'].append(dict(request=text, slots=slots, sameRecord=True,
                                     fullFields=True, reply=response['reply']))
        print(json.dumps(dict(request=text, passed=True)), flush=True)
    report['passed'] = True
except Exception as exc:
    report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:250])
(ROOT/'docs/audit/live_everything_verification.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps(dict(passed=report.get('passed'), error=report.get('error'))), flush=True)
if not report.get('passed'):
    raise SystemExit(1)
