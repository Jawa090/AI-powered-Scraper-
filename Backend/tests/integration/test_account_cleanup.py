import uuid
import pytest
from sqlalchemy import select, update, func
from langchain_core.messages import AIMessage
from Database.controller import session_scope
from Database.models.user import User
from Database.models.session import AgentSession
from Database.models.query import Query
from Database.models.job import Job
from Database.models.dataset import Dataset, DatasetRecord
from Database.models.lead import Lead
from Database.models.message import AgentMessage
from Database.models.action import AgentAction
from services.account_cleanup import purge_accounts
from services.jobs import enqueue_scrape
from scrappers.controller import validate_params, describe_for_llm
from scrappers.base import InvalidScrapeParams


def test_jwiz_missing_location_is_rejected_before_any_job_or_approval():
    from Database.search import SearchCriteria
    from agents.graph.nodes.validate_proposal import validate_proposal
    slots=dict(record_kind='company',category='roofing',quantity=5,location_scope='any',
               has_email=True,has_phone=True,source='jwiz')
    criteria=SearchCriteria.from_slots(slots)
    result=validate_proposal({'slots':slots,'request_intent':'records','turn_id':'test',
        'last_search':{'turn_id':'test','slots_hash':criteria.fingerprint(),'total':0},
        'messages':[AIMessage(content='',tool_calls=[{'id':'proposal','name':'propose_scrape',
             'args':{'source':'jwiz','quantity':5}}])]})
    assert result['pending_proposal'] is None
    assert 'requires a city or state' in result['messages'][0].content
    with session_scope() as db:
        before=db.scalar(select(func.count(Job.id)))
        with pytest.raises(InvalidScrapeParams,match='requires a city or state'):
            enqueue_scrape(db,user=db.scalars(select(User)).first(),script_id='jwiz',params={'limit':5})
        assert db.scalar(select(func.count(Job.id)))==before
    assert validate_params('jwiz',{'us_state':'NY','limit':5}).us_state=='NY'
    assert next(row for row in describe_for_llm() if row['id']=='jwiz')['requires_location']


def test_terminal_job_status_is_fresh_context_instead_of_old_queue_claim():
    from agents.graph.nodes.load_context import load_context, build_system_prompt
    tag=uuid.uuid4().hex
    with session_scope() as db:
        user=User(id='status-'+tag,username='status-'+tag,name='Status test',role='user',auth_source='db')
        db.add(user);db.flush()
        db.add(AgentSession(id=tag,user_id=user.id,agent_id='agent-master',department_id='dept-default'));db.flush()
        db.add(Job(id=tag,name='Failed source',status='Failed',script_id='jwiz',created_by=user.id,
                   error_message='Location required'))
        db.flush();db.add(Query(id=tag,user_id=user.id,session_id=tag,job_id=tag));db.flush()
    state={'session_id':tag,'messages':[AIMessage(content='JWiz is queued')]}
    loaded=load_context(state)
    assert loaded['current_jobs'][0]['status']=='Failed'
    assert 'logs' not in loaded['current_jobs'][0]
    assert 'authoritative' in build_system_prompt({**state,**loaded})


def test_account_purge_removes_history_but_preserves_shared_data():
    from settings import settings
    from services.ingest import upsert_leads
    tag=uuid.uuid4().hex
    with session_scope() as db:
        # Roll back the purge so this test cannot affect any other fixture accounts.
        nested=db.begin_nested()
        db.execute(update(Job).where(Job.status.in_(['Running','WaitingForUser'])).values(status='Cancelled'))
        keeper=User(id='keep-'+tag,username='keep-'+tag,name='Kept user',role='user',auth_source='db')
        removed=User(id='remove-'+tag,username='remove-'+tag,name='Removed user',role='user',auth_source='db')
        db.add_all([keeper,removed]);db.flush()
        sid='session-'+tag
        db.add(AgentSession(id=sid,user_id=removed.id,agent_id='agent-master',department_id='dept-default'));db.flush()
        db.add(AgentMessage(id='message-'+tag,session_id=sid,sender='user',role='user',text='Private history'))
        db.add(AgentAction(id='action-'+tag,user_id=removed.id,session_id=sid,action_type='query_execute',title='Private activity'))
        private=Dataset(id='private-'+tag,name='Removed dataset',created_by=removed.id)
        shared=Dataset(id='shared-'+tag,name='Kept dataset',created_by=keeper.id)
        db.add_all([private,shared]);db.flush()
        result=upsert_leads(db,[dict(source_code='jwiz',record_kind='company',external_id=tag+str(index),
            organization_name=tag+str(index)) for index in range(2)],dataset_id=private.id)
        first,second=result.lead_ids
        db.add(DatasetRecord(dataset_id=shared.id,lead_id=first));db.flush()
        report=purge_accounts(db,{settings.AUTH_USER_USERNAME,settings.AUTH_ADMIN_USERNAME,keeper.username},
                             email_updates={keeper.username:'updated@example.test'},apply=True)
        assert report['applied']
        assert db.scalar(select(User.id).where(User.id==removed.id)) is None
        assert db.scalar(select(AgentMessage.id).where(AgentMessage.session_id==sid)) is None
        assert db.scalar(select(AgentAction.id).where(AgentAction.user_id==removed.id)) is None
        assert db.scalar(select(Dataset.id).where(Dataset.id==private.id)) is None
        assert db.scalar(select(Lead.id).where(Lead.id==first))==first
        assert db.scalar(select(Lead.id).where(Lead.id==second)) is None
        assert db.scalar(select(User.email).where(User.id==keeper.id))=='updated@example.test'
        nested.rollback()
