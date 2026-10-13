"""Reproduce the reported short contact answer with real AI in the isolated DB."""
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
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from agents.graph.checkpointer import setup_checkpointer
from agents.graph.runner import run_turn
from services.sessions import new_session
setup_checkpointer()
uid = 'both-check-' + uuid.uuid4().hex
with session_scope() as db:
    user = User(id=uid, username=uid, email=uid+'@example.test', name='Both contacts audit',
                role='user', status='Active', department_id='dept-default', auth_source='db')
    db.add(user); db.flush()
sid = new_session(user)
report = {'realProvider': True, 'isolatedDatabase': True, 'scrapeApproved': False}
try:
    initial = run_turn(user, sid, 'get me 1 general contractor from new york', uuid.uuid4().hex)
    assert initial['decision'] == 'CLARIFY' and not initial['records']
    response = run_turn(user, sid, 'both', uuid.uuid4().hex)
    with session_scope() as db:
        query = db.get(Query, response['queryId'])
        slots = query.parameters['slots']
        trace = query.parameters['trace']
    assert slots['has_email'] and slots['has_phone']
    assert not response['missingRequirements'] and not response.get('jobId')
    assert any(event.get('tool_name') == 'search_leads' for event in trace)
    assert response.get('pendingAction') or response.get('records')
    report.update(passed=True, slots=slots, searchedSuccessfully=True, pendingAction=bool(response.get('pendingAction')),
                  decision=response['decision'], reply=response['reply'])
except Exception as exc:
    report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:250])
(ROOT/'docs/audit/live_both_contacts_verification.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps(report, default=str), flush=True)
if not report.get('passed'):
    raise SystemExit(1)
