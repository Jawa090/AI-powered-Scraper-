"""Check model-written greeting requirements against the isolated PostgreSQL DB."""
import json,sys,uuid,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name=json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL=make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL=make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
settings.LLM_MAX_RETRIES=0;settings.LLM_TIMEOUT_S=25
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.job import Job
from services.sessions import new_session
from agents.graph.runner import run_turn
from agents.graph.checkpointer import setup_checkpointer
setup_checkpointer()
uid='greeting-check-'+uuid.uuid4().hex
with session_scope() as db:
    user=User(id=uid,username=uid,email=uid+'@example.test',name='Greeting verification',role='user',status='Active',department_id='dept-default',auth_source='db')
    db.add(user);db.flush()
sid=new_session(user)
report={'realProvider':True,'isolatedDatabase':True,'checks':[]}
try:
    for text in ['hi','hello']:
        response=run_turn(user,sid,text,uuid.uuid4().hex)
        reply=response['reply'].lower()
        assert re.search(r'(?m)^\s*(?:[-*•]|\d+[.)])',reply), 'Missing requirements list'
        assert any(term in reply for term in ['trade','category','industry'])
        assert 'city' in reply and 'state' in reply
        assert any(term in reply for term in ['quantity','number','how many'])
        assert 'email' in reply and 'phone' in reply
        assert any(term in reply for term in ['compan','contractor']) and any(term in reply for term in ['bid','opportunit'])
        assert response['decision']=='NONE' and not response.get('jobId') and not response.get('records') and not response.get('pendingAction')
        with session_scope() as db:
            query=db.get(Query,response['queryId'])
            assert all(event.get('tool_name') not in ['search_leads','propose_scrape'] for event in query.parameters.get('trace',[]))
            assert db.query(Job).filter_by(created_by=uid).count()==0
        report['checks'].append({'greeting':text,'reply':response['reply'],'decision':response['decision'],'requirementsList':True,'noSearchOrScrape':True})
    report['passed']=True
except Exception as exc:
    report.update(passed=False,errorType=type(exc).__name__,error=str(exc)[:250])
(ROOT/'docs/audit/live_greeting_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
