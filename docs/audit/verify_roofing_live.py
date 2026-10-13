"""Verify the exact roofing request using genuine sources and the configured DB."""
import sys,json,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from settings import settings
settings.SCRAPER_MODE='live';settings.SELENIUM_MODE='local'
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.job import Job
from agents.graph.runner import run_turn,run_event_turn
from agents.graph.checkpointer import setup_checkpointer
from services.sessions import new_session
from services.delivery import delivery_rows
import worker
assert json.loads((ROOT/'docs/audit/configured_database_migration.json').read_text())['applied']
setup_checkpointer()
with session_scope() as db: admin=db.get(User,'usr-env-admin')
sid=new_session(admin)
report={'database':'configured','syntheticRecordsWritten':False,'requested':10}
try:
    response=run_turn(admin,sid,'Get 10 roofing constructors from NY newyork. Companies, no contact requirement.',uuid.uuid4().hex)
    initial=response.get('records') or []
    with session_scope() as db:
        origin=db.get(Query,response['queryId'])
        report['slots']=origin.parameters['slots']
    if response.get('pendingAction'):
        proposal=response['pendingAction']['proposal']
        assert proposal['source']=='jwiz'
        response=run_turn(admin,sid,'Yes, run this exact scrape.',uuid.uuid4().hex,expected_proposal_id=proposal['tool_call_id'])
        job_id=response['jobId']
        worker.execute_job(job_id,'live-roofing-verification')
        response=run_event_turn(sid,job_id)
    rows={r['id']:r for r in [*initial,*(response.get('records') or [])]}
    assert rows and all(r['recordKind']=='company' and r['city']=='New York' and r['state']=='NY'
        and 'roofing' in r['category'].lower() for r in rows.values())
    with session_scope() as db:
        assert delivery_rows(db,response['queryId'])==response['records']
        job=db.get(Job,response.get('jobId')) if response.get('jobId') else None
        report.update(jobStatus=job.status if job else None,sourceRecordsScanned=job.records_found if job else None)
    report.update(returned=len(rows),shortfall=10-len(rows),queryId=response['queryId'],jobId=response.get('jobId'),
        reply=response['reply'],snapshotMatches=True,correctTradeTypeAndLocation=True,passed=True)
except Exception as exc:
    report.update(passed=False,errorType=type(exc).__name__,error=str(exc)[:300])
(ROOT/'docs/audit/live_roofing_flow.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
