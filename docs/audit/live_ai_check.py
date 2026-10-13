"""Real provider intent check against controlled, disposable PostgreSQL data."""
import json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name=json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL=make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL=make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
settings.LLM_MAX_RETRIES=0; settings.LLM_TIMEOUT_S=25
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from services.auth import hash_password
from services.ingest import upsert_leads
from services.sessions import new_session
from agents.graph.runner import run_turn
from agents.graph.checkpointer import setup_checkpointer
setup_checkpointer()
uid='intent-check-'+uuid.uuid4().hex
with session_scope() as db:
    user=User(id=uid,username=uid,email=uid+'@example.test',name='Intent verification',role='user',status='Active',department_id='dept-default',auth_source='db')
    db.add(user);db.flush()
    upsert_leads(db,[{'source_code':'jwiz','record_kind':'company','external_id':uid+'-'+str(i),
        'organization_name':'Verification Roofing '+str(i)+' '+uid,'category':'Roofing','city':'New York','us_state':'NY',
        'email':uid+str(i)+'@example.test','source_url':'https://example.test/'+uid+'/'+str(i)} for i in range(12)])
sid=new_session(user)
report={'realProvider':True,'controlledTestData':True,'request':'10 roofing constructors from NY newyork'}
try:
    response=run_turn(user,sid,report['request'],'live-intent-'+uuid.uuid4().hex)
    assert response['decision']=='CLARIFY' and not response.get('records') and not response.get('pendingAction')
    report['initialClarification']=response['reply']
    response=run_turn(user,sid,'Neither email nor phone is required','live-intent-'+uuid.uuid4().hex)
    with session_scope() as db: query=db.get(Query,response['queryId']);slots=(query.parameters or {}).get('slots')
    report.update(slots=slots,returned=len(response.get('records',[])),reply=response['reply'],jobQueued=bool(response.get('jobId')))
    from Database.search import category_terms
    assert category_terms(slots['category']) == ['roofing'] and slots['city']=='New York' and slots['us_state']=='NY'
    assert slots['record_kind']=='company' and slots['quantity']==10
    assert len(response['records'])==10 and not response.get('jobId')
    assert all(row['city']=='New York' and row['state']=='NY' and 'roofing' in row['category'].lower() for row in response['records'])
    report['passed']=True
except Exception as exc:
    report.update(passed=False,errorType=type(exc).__name__,error=str(exc)[:200])
(ROOT/'docs/audit/live_ai_verification.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
print(json.dumps(report,default=str),flush=True)
