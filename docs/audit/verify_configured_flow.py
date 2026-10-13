"""Verify real provider, live worker and delivery audit in the configured database.

Only genuine source records are written. Run explicitly after the approved migration.
"""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Backend'), str(ROOT)]
from settings import settings
settings.SCRAPER_MODE = 'live'
settings.SELENIUM_MODE = 'local'
from sqlalchemy import select
from fastapi.testclient import TestClient
from app import app
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.job import Job
from Database.models.source import Source
from agents.graph.runner import run_turn, run_event_turn
from agents.graph.graph import get_compiled_graph
from agents.graph.checkpointer import setup_checkpointer
from services.sessions import new_session
from services.auth import create_access_token
import worker


assert json.loads((ROOT / 'docs/audit/configured_database_migration.json').read_text())['applied']
setup_checkpointer()
with session_scope() as db:
    admin = db.get(User, 'usr-env-admin')
    assert admin and admin.status == 'Active'
sid = new_session(admin)
report = {'database': 'configured', 'syntheticRecordsWritten': False, 'checks': []}
if len(sys.argv) > 1:
    report['checks'] = json.loads((ROOT / 'docs/audit/configured_flow_verification.json').read_text())['checks']
requests = [
    ('jwiz', 'Get 2 roofing contractor companies from Yonkers, NY using JWiz. No contact requirement.'),
    ('dasny', 'Get 2 current bid opportunities from DASNY statewide in New York state. Any category, no contact requirement.'),
    ('bonfire', 'Get 2 current bid opportunities from Bonfire in Dallas, TX. Any category, no contact requirement.'),
    ('nyscr', 'Get 2 current bid opportunities from NYSCR statewide in New York state. Any category, no contact requirement.'),
]
try:
    for source, text in requests:
        if len(sys.argv) > 1 and source != sys.argv[1]:
            continue
        print('Checking live request for ' + source, flush=True)
        response = run_turn(admin, sid, text, 'configured-check-' + uuid.uuid4().hex, new_only=(source == 'nyscr'))
        initial_id = response['queryId']
        initial_rows = response.get('records') or []
        pending = response.get('pendingAction')
        if pending:
            proposal = pending['proposal']
            assert proposal['source'] == source, 'Unexpected source in proposed scrape'
            response = run_turn(admin, sid, 'Yes, run this exact scrape.', 'configured-approval-' + uuid.uuid4().hex,
                expected_proposal_id=proposal['tool_call_id'])
            assert response.get('jobId'), 'Approved request did not enqueue a job'
            worker.execute_job(response['jobId'], 'configured-verification')
            response = run_event_turn(sid, response['jobId'])
        rows = response.get('records') or []
        with session_scope() as db:
            query = db.get(Query, initial_id)
            slots = query.parameters.get('slots', {})
            from services.delivery import delivery_rows
            assert delivery_rows(db, response['queryId']) == rows
            assert all(db.scalar(select(Source.id).where(Source.code == row['sourceCode'])) for row in rows)
        delivered = {row['id']: row for row in [*initial_rows, *rows]}
        assert len(delivered) == 2, 'Live request did not deliver the requested two distinct records'
        assert all(row['sourceCode'] == source for row in rows)
        if source == 'jwiz':
            assert all(row['city'] == 'Yonkers' and row['state'] == 'NY' and 'roofing' in row['category'].lower() for row in rows)
        report['checks'] = [check for check in report['checks'] if check['source'] != source]
        report['checks'].append({'source': source, 'slots': slots, 'returned': len(delivered),
            'initialReturned': len(initial_rows), 'completionReturned': len(rows) if response.get('jobId') else 0,
            'jobId': response.get('jobId'), 'queryId': response['queryId'], 'snapshotMatches': True})
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + create_access_token(admin)}
    groups = client.get('/api/admin/deliveries', headers=headers, params={'user_id': admin.id}).json()['groups']
    assert groups[0]['heading'] == 'admin'
    delivered_ids = {row['queryId'] for row in groups[0]['deliveries']}
    assert all(check['queryId'] in delivered_ids for check in report['checks'])
    report.update(adminHeadingVerified=True, passed=True)
except Exception as exc:
    report.update(passed=False, errorType=type(exc).__name__, error=str(exc)[:250])
(ROOT / 'docs/audit/configured_flow_verification.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
print(json.dumps(report, default=str), flush=True)
