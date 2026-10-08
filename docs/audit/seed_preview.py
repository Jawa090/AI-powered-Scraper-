"""Controlled browser deliveries, confined to the allocated test database."""
import sys,json,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name=json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL=make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL=make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
from Database.controller import session_scope
from Database.models.user import User
from Database.models.lead import Lead
from Database.models.query import Query
from Database.models.message import AgentMessage
from services.sessions import new_session
from services.delivery import record_delivery
from services.auth import hash_password
from routes.serializers import serialize_lead
report=json.loads((ROOT/'docs/audit/live_jwiz_positive.json').read_text())
with session_scope() as db:
    user=db.get(User,'browser-preview-user')
    if not user:
        user=User(id='browser-preview-user',username='PreviewUser',name='Browser verification',email='preview-user@example.test',
            role='user',status='Active',department_id='dept-default',auth_source='db',password_hash=hash_password('PreviewPassword123'))
        db.add(user);db.flush()
    admin=db.get(User,'usr-env-admin')
for owner in [admin,user]:
    sid=new_session(owner);qid='browser-preview-'+uuid.uuid4().hex
    with session_scope() as db:
        records=[serialize_lead(db.get(Lead,row['id'])) for row in report['savedRecords'] if db.get(Lead,row['id'])]
        assert len(records)==2
        q=Query(id=qid,user_id=owner.id,session_id=sid,query_text='Roofing companies in Yonkers NY',status='completed',decision='DB',
            parameters={'slots':{'category':'Roofing','city':'Yonkers','us_state':'NY','quantity':2,'record_kind':'company'}})
        db.add(q);db.flush();record_delivery(db,q,records)
        reply='Browser verification: two live roofing companies from Yonkers NY.'
        q.response={'reply':reply,'records':records,'total':2,'sessionId':sid,'queryId':qid}
        db.add(AgentMessage(id=qid+':agent',session_id=sid,sender='agent',role='agent',text=reply,
            message_metadata={'queryId':qid,'records':records,'total':2}))
print('Preview deliveries prepared for administrator and preview-user@example.test.',flush=True)
