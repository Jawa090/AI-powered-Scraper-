"""Verify the live model's requirements gate against the isolated audit database."""
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
settings.LLM_MAX_RETRIES = 0
settings.LLM_TIMEOUT_S = 25
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.job import Job
from services.sessions import new_session
from agents.graph.runner import run_turn
from agents.graph.checkpointer import setup_checkpointer

setup_checkpointer()
uid = 'requirements-check-' + uuid.uuid4().hex
with session_scope() as db:
    user = User(id=uid, username=uid, email=uid+'@example.test', name='Requirements verification',
                role='user', status='Active', department_id='dept-default', auth_source='db')
    db.add(user)
    db.flush()
sid = new_session(user)
report = {'realProvider': True, 'isolatedDatabase': True, 'checks': []}
try:
    for index, text in enumerate(['1 roofing contractor', 'New York city, NY',
                                 'Neither email nor phone is required', '2 plumbing contractors']):
        response = run_turn(user, sid, text, uuid.uuid4().hex)
        with session_scope() as db:
            query = db.get(Query, response['queryId'])
            params = query.parameters or {}
            slots = params.get('slots', {})
            trace = params.get('trace', [])
            assert db.query(Job).filter_by(created_by=uid).count() == 0
        missing = response.get('missingRequirements', [])
        if index in (0, 1, 3):
            assert missing and response['decision'] == 'CLARIFY'
            reply = response['reply'].lower()
            assert 'dsml' not in reply and 'email' in reply and 'phone' in reply, 'Expected a human-readable clarification'
            if index != 1:
                assert 'location' in reply or ('city' in reply and 'state' in reply)
            assert not response.get('records') and not response.get('pendingAction') and not response.get('jobId')
            assert not trace, 'Incomplete request accessed knowledge or data tools'
            assert slots['has_email'] is None and slots['has_phone'] is None
            if index != 1:
                assert not slots.get('city') and not slots.get('us_state')
            else:
                assert len(missing) == 1 and 'contact' in missing[0]
        else:
            assert not missing and slots['has_email'] is False and slots['has_phone'] is False
            assert slots['city'] == 'New York' and slots['us_state'] == 'NY' and slots['quantity'] == 1
            assert any(event.get('tool_name') == 'search_leads' for event in trace), 'Complete request did not search'
        report['checks'].append({'request': text, 'reply': response['reply'], 'slots': slots,
                                 'missingRequirements': missing, 'decision': response['decision'],
                                 'toolTrace': trace, 'noJobEnqueued': True})
        print(json.dumps({'turn': index+1, 'decision': response['decision'], 'missingRequirements': missing}), flush=True)
    report['passed'] = True
except Exception as exc:
    report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:250],
                  failedRequest=text, failedResponse=response, failedSlots=slots)
(ROOT / 'docs/audit/live_requirements_verification.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps({'passed': report.get('passed'), 'error': report.get('error')}), flush=True)
if not report.get('passed'):
    raise SystemExit(1)
