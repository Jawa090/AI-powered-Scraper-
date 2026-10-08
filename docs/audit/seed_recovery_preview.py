"""Prepare UI-only audit accounts using frozen genuine live recovery rows."""
import json, sys, uuid
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
from Database.models.message import AgentMessage
from services.auth import hash_password
from services.sessions import new_session
from services.delivery import record_delivery
report = json.loads((ROOT/'docs/audit/live_recovery_verification.json').read_text())
assert report['passed']
with session_scope() as db:
    original = db.get(Query, report['checks'][-1]['queryId'])
    response, params = dict(original.response), dict(original.parameters)
for role, username, email in [('user', 'RecoveryPreview', 'recovery-preview@example.test'), ('admin', 'RecoveryAdmin', 'recovery-admin@example.test')]:
    with session_scope() as db:
        user = db.get(User, 'usr-env-admin') if role == 'admin' else db.query(User).filter_by(username=username).first()
        if not user:
            user = User(id='ui-recovery-'+uuid.uuid4().hex, username=username, email=email, role=role,
                        name='Recovery UI audit', auth_source='db', status='Active', department_id='dept-default',
                        password_hash=hash_password('TestRecovery123'))
            db.add(user); db.flush()
        if role == 'admin':
            user.username, user.auth_source = username, 'db'
            user.password_hash = hash_password('TestRecovery123')
            db.flush()
    sid, qid = new_session(user), 'ui-recovery-'+uuid.uuid4().hex
    with session_scope() as db:
        q = Query(id=qid, user_id=user.id, session_id=sid, query_text=original.query_text, job_id=original.job_id,
                  parameters=params, status='completed', decision='SCRAPER')
        db.add(q); db.flush()
        record_delivery(db, q, response['records'])
        q.response = {**response, 'sessionId': sid, 'queryId': qid}
        db.add(AgentMessage(id=qid+':agent', session_id=sid, sender='agent', role='agent', text=response['reply'],
            message_metadata={key: val for key, val in q.response.items() if key not in ('reply', 'sessionId')}))
print('Isolated recovery UI audit accounts prepared with genuine frozen source data.')
