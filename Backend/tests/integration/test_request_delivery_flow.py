"""Exercise the real graph/tools, PostgreSQL worker, snapshots and admin API.

Only external AI and website responses are scripted; persistence is real.
"""
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from Database.controller import session_scope
from Database.models.user import User
from Database.models.query import Query
from Database.models.session_event import SessionEvent
from Database.models.message import AgentMessage
from Database.models.lead import Lead
from services.auth import hash_password, create_access_token
from services.ingest import upsert_leads
from agents.graph.graph import build_agent_graph
from agents.graph.runner import run_turn, run_event_turn
from agents.llm.chat_model import LLMUnavailable
from app import app


@pytest.fixture
def account():
    uid = 'test-' + uuid.uuid4().hex
    with session_scope() as db:
        user = User(id=uid, username=uid, name='Test user', email=uid + '@example.test', role='user', status='Active',
            auth_source='db', password_hash=hash_password('test-password'), department_id='dept-default')
        db.add(user); db.flush()
    return user


def record(tag, index, city='New York', category=None):
    return {'source_code': 'jwiz', 'record_kind': 'company', 'external_id': f'{tag}-{index}',
        'organization_name': f'Flow roofer {tag} {index}', 'category': category or tag,
        'city': city, 'us_state': 'NY', 'email': f'{tag}-{index}@example.test',
        'source_url': f'https://example.test/{tag}/{index}'}


@pytest.fixture
def scripted_graph(monkeypatch):
    import agents.graph.graph as wiring
    import agents.graph.runner as runner
    import agents.graph.nodes.confirmation as confirmation
    import agents.graph.nodes.rag_retrieve as retrieval
    # Import the module explicitly because the package exports a same-name node.
    import importlib
    retrieval = importlib.import_module('agents.graph.nodes.rag_retrieve')
    monkeypatch.setattr(retrieval.rag_client, 'status', lambda: {'state': 'not_deployed', 'available': False})
    def configure(category, quantity):
        def agent(state):
            if state.get('active_job_id'):
                return {'messages': [AIMessage(content='The approved scrape is queued.')]}
            last = state['messages'][-1]
            if getattr(last, 'type', '') == 'tool' and last.tool_call_id.startswith('search-'):
                result = json.loads(last.content)
                if result['sufficient']:
                    return {'messages': [AIMessage(content=f"Found {result['returned']} matching companies.")]}
                return {'messages': [AIMessage(content='', tool_calls=[{'id': 'proposal-' + uuid.uuid4().hex,
                    'name': 'propose_scrape', 'args': {'source': 'jwiz', 'quantity': quantity}}])]}
            return {'messages': [AIMessage(content='', tool_calls=[{'id': 'search-' + uuid.uuid4().hex,
                'name': 'search_leads', 'args': {'category': category, 'city': 'newyork', 'us_state': 'NY',
                    'quantity': (state.get('slots') or {}).get('quantity', quantity), 'record_kind': 'company', 'has_email': True}}])]}
        import agents.graph.nodes.gather_requirements as interpretation
        def interpret(state):
            return {'request_intent': 'records', 'intent_interpreted': True, 'requirements_met': True,
                'missing_requirements': [], 'slots': {'category': category, 'city': 'New York', 'us_state': 'NY',
                    'quantity': quantity, 'record_kind': 'company', 'has_email': True, 'has_phone': False}}
        monkeypatch.setattr(interpretation, 'interpret_request', interpret)
        monkeypatch.setattr(wiring, 'call_model', agent)
        graph = build_agent_graph(MemorySaver())
        monkeypatch.setattr(runner, 'get_compiled_graph', lambda: graph)
        monkeypatch.setattr('routes.bot.get_compiled_graph', lambda: graph)
        monkeypatch.setattr(confirmation, 'get_chat_model', lambda: object())
        monkeypatch.setattr(confirmation, 'invoke_llm', lambda *args, **kwargs: AIMessage(content='Run this exact scrape?'))
        monkeypatch.setattr(runner, 'classify_confirmation', lambda text, pending: {'decision': 'approve', 'text': text})
        return graph
    return configure


def test_real_graph_returns_ten_frozen_rows_and_replays_original(account, scripted_graph):
    tag = 'roofing-' + uuid.uuid4().hex
    with session_scope() as db:
        saved = upsert_leads(db, [record(tag, i) for i in range(12)] + [record(tag, 99, city='Albany')])
        assert saved.failed == 0
    scripted_graph(tag, 10)
    sid = 'session-' + uuid.uuid4().hex
    response = run_turn(account, sid, '10 roofing constructors from NY newyork', 'request-1')
    assert len(response['records']) == response['total'] == 10
    assert response['totalAvailable'] == 12
    assert all(row['city'] == 'New York' and row['state'] == 'NY' for row in response['records'])
    first = response['records'][0]
    with session_scope() as db:
        lead = db.get(Lead, first['id']); lead.lead_metadata = {**lead.lead_metadata, 'email': 'new@example.test'}
    replay = run_turn(account, sid, 'same retry', 'request-1')
    assert replay == response
    client = TestClient(app)
    with session_scope() as db:
        admin = db.get(User, 'usr-env-admin'); token = create_access_token(admin)
    delivered = client.get('/api/admin/deliveries', headers={'Authorization': 'Bearer ' + token}).json()
    group = next(g for g in delivered['groups'] if g['userId'] == account.id)
    assert group['heading'] == account.email
    assert group['deliveries'][0]['records'] == response['records']
    assert any(g['heading'] == 'admin' for g in delivered['groups'])
    import csv, io
    exported = client.get('/api/admin/deliveries/export.csv', params={'query_id': response['queryId']},
        headers={'Authorization': 'Bearer ' + token})
    assert exported.status_code == 200
    csv_rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(csv_rows) == 10
    assert {row['User'] for row in csv_rows} == {account.email}
    assert csv_rows[0]['Email'] == first['email']
    assert csv_rows[0]['Historical Snapshot'] == 'True'
    detail = client.get('/api/admin/requests/' + response['queryId'], headers={'Authorization': 'Bearer ' + token}).json()
    assert detail['request']['queryText'] == '10 roofing constructors from NY newyork'
    assert [message['sender'] for message in detail['transcript']] == ['user', 'agent']
    assert detail['rowsServed'][0]['leadId'] == first['id']
    assert detail['rowsServed'][0]['email'] == first['email']
    assert client.get('/api/admin/deliveries/export.csv', headers={
        'Authorization': 'Bearer ' + create_access_token(account)}).status_code == 403
    denied = client.get('/api/admin/deliveries', headers={'Authorization': 'Bearer ' + create_access_token(account)})
    assert denied.status_code == 403


def test_approval_worker_completion_filters_and_survives_ai_outage(account, scripted_graph, monkeypatch):
    tag = 'roofing-' + uuid.uuid4().hex
    scripted_graph(tag, 10)
    sid = 'session-' + uuid.uuid4().hex
    proposal = run_turn(account, sid, '10 roofers in New York NY with email', 'initial')
    assert proposal['pendingAction'] and not proposal['jobId']
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as stale:
        run_turn(account, sid, 'Yes, run it.', 'stale', expected_proposal_id='old-proposal')
    assert stale.value.status_code == 409
    approval = run_turn(account, sid, 'Yes, run it.', 'approved',
        expected_proposal_id=proposal['pendingAction']['proposal']['tool_call_id'])
    assert approval['jobId']
    assert run_turn(account, sid, 'Yes, run it.', 'approved') == approval
    import worker
    from scrappers.base import StandardRecord
    rows = [StandardRecord(**record(tag, i)) for i in range(10)]
    rows += [StandardRecord(**record(tag, 98, city='Albany')), StandardRecord(**record(tag, 99, category='plumbing'))]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows))
    worker.execute_job(approval['jobId'], 'test-worker')
    with session_scope() as db:
        event = db.scalar(select(SessionEvent).where(SessionEvent.session_id == sid))
        assert event.status == 'pending'
        original = db.get(Query, proposal['queryId'])
        assert original.records_returned == 0  # Initial response is immutable.
    import agents.graph.runner as runner
    def unavailable(*args, **kwargs):
        raise LLMUnavailable('timeout')
    monkeypatch.setattr(runner, 'invoke_llm', unavailable)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        run_event_turn(sid, approval['jobId'])
    assert error.value.status_code == 503
    with session_scope() as db:
        assert db.scalar(select(SessionEvent).where(SessionEvent.session_id == sid)).status == 'pending'
    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(content='Here are 10 matching roofing companies.'))
    completion = run_event_turn(sid, approval['jobId'])
    assert completion['total'] == len(completion['records']) == 10
    assert all(row['city'] == 'New York' and row['category'] == tag for row in completion['records'])
    assert completion['requestFulfilled'] is True
    assert completion['recoveredRecords'] == 12  # Matching and unrelated rows are all stored.
    assert run_event_turn(sid, approval['jobId'])['alreadyDelivered']
    with session_scope() as db:
        messages = db.scalars(select(AgentMessage).where(AgentMessage.session_id == sid)).all()
        assert any(m.sender == 'user' and m.text == 'Yes, run it.' for m in messages)


def test_incomplete_request_waits_across_followups_before_any_data_lookup(account, monkeypatch):
    import importlib
    interpretation = importlib.import_module('agents.graph.nodes.gather_requirements')
    agent = importlib.import_module('agents.graph.nodes.agent')
    retrieval = importlib.import_module('agents.graph.nodes.rag_retrieve')
    import agents.graph.runner as runner
    category = 'roofing-' + uuid.uuid4().hex
    with session_scope() as db:
        assert upsert_leads(db, [record(category, 1)]).failed == 0
    def parse(schema, messages):
        payload = json.loads(messages[-1].content)
        text = payload['latestMessage']
        if text == '1 roofing contractor':
            criteria = dict(record_kind='company', category=category, quantity=1)
        else:
            criteria = {}
            if text == 'New York city, NY':
                criteria.update(city='New York', us_state='NY', location_scope='city')
            elif text == 'Neither email nor phone is required':
                criteria.update(has_email=False, has_phone=False)
        return {'intent': 'records', 'criteria': criteria, 'is_followup': text != '1 roofing contractor'}
    monkeypatch.setattr(interpretation, 'invoke_structured', parse)
    kb_calls = []
    monkeypatch.setattr(retrieval.rag_client, 'status', lambda: kb_calls.append(True) or {'state': 'not_deployed', 'available': False})
    tool_bindings = []
    monkeypatch.setattr(agent, 'get_chat_model', lambda **kwargs: tool_bindings.append(kwargs) or object())
    def answer(model, messages):
        if 'Requirements Incomplete' in messages[0].content:
            return AIMessage(content='Please supply the missing location and/or contact requirements.')
        if isinstance(messages[-1], __import__('langchain_core.messages', fromlist=['ToolMessage']).ToolMessage):
            return AIMessage(content='Found 1 matching roofing company.')
        return AIMessage(content='', tool_calls=[{'id': 'complete-search', 'name': 'search_leads', 'args': {}}])
    monkeypatch.setattr(agent, 'invoke_llm', answer)
    graph = build_agent_graph(MemorySaver())
    monkeypatch.setattr(runner, 'get_compiled_graph', lambda: graph)
    sid = 'session-' + uuid.uuid4().hex
    initial = run_turn(account, sid, '1 roofing contractor', 'partial-1')
    assert initial['decision'] == 'CLARIFY' and initial['records'] == [] and not initial['jobId']
    assert initial['missingRequirements'] and kb_calls == [] and tool_bindings == [{}]
    location = run_turn(account, sid, 'New York city, NY', 'partial-2')
    assert location['decision'] == 'CLARIFY' and location['records'] == [] and not location['jobId']
    assert len(location['missingRequirements']) == 1 and 'contact' in location['missingRequirements'][0]
    assert kb_calls == [] and tool_bindings == [{}, {}]
    complete = run_turn(account, sid, 'Neither email nor phone is required', 'complete')
    assert len(complete['records']) == 1 and complete['missingRequirements'] == []
    assert complete['decision'] == 'DB' and not complete['jobId'] and kb_calls == [True]
    with session_scope() as db:
        assert db.get(Query, initial['queryId']).parameters['trace'] == []
        assert db.get(Query, location['queryId']).parameters['trace'] == []


def test_more_records_exposes_action_and_click_delivers_two_unseen_rows(account, monkeypatch):
    import importlib
    import agents.graph.runner as runner
    import agents.graph.nodes.confirmation as confirmation
    import worker
    from scrappers.base import StandardRecord
    from Database.models.job import Job
    interpretation = importlib.import_module('agents.graph.nodes.gather_requirements')
    agent = importlib.import_module('agents.graph.nodes.agent')
    retrieval = importlib.import_module('agents.graph.nodes.rag_retrieve')
    category = 'general contractor-' + uuid.uuid4().hex
    with session_scope() as db:
        upsert_leads(db, [record(category, 0)])
    def parse(schema, messages):
        text = json.loads(messages[-1].content)['latestMessage']
        if text == 'now get me 2 more':
            return {'intent': 'records', 'is_followup': True, 'additional_records': True,
                    'criteria': {'quantity': 2}}
        return {'intent': 'records', 'criteria': dict(record_kind='company', category=category,
            city='New York', us_state='NY', location_scope='city', quantity=1, has_email=False, has_phone=False)}
    monkeypatch.setattr(interpretation, 'invoke_structured', parse)
    monkeypatch.setattr(retrieval.rag_client, 'status', lambda: {'state': 'not_deployed', 'available': False})
    monkeypatch.setattr(agent, 'get_chat_model', lambda **kwargs: object())
    def answer(model, messages):
        if isinstance(messages[-1], ToolMessage):
            # A shortage must become an action even when the AI would only offer one.
            return AIMessage(content='Shall I go ahead and propose that scrape?')
        return AIMessage(content='', tool_calls=[{'id': uuid.uuid4().hex, 'name': 'search_leads', 'args': {}}])
    monkeypatch.setattr(agent, 'invoke_llm', answer)
    monkeypatch.setattr(confirmation, 'get_chat_model', lambda: object())
    monkeypatch.setattr(confirmation, 'invoke_llm', lambda *args, **kwargs: AIMessage(content='Click Action to collect 2 more matching contractors from JWiz.'))
    monkeypatch.setattr(runner, 'classify_confirmation', lambda text, pending: {'decision': 'approve', 'text': text})
    graph = build_agent_graph(MemorySaver())
    monkeypatch.setattr(runner, 'get_compiled_graph', lambda: graph)
    monkeypatch.setattr('routes.bot.get_compiled_graph', lambda: graph)
    sid = 'session-' + uuid.uuid4().hex
    first = run_turn(account, sid, 'Get 1 general contractor in New York NY; neither contact required', 'first')
    assert len(first['records']) == 1 and not first['pendingAction']
    more = run_turn(account, sid, 'now get me 2 more', 'more')
    assert more['pendingAction'] and more['proposedActions'] and not more['jobId']
    assert more['records'] == [] and more['totalAvailable'] == 0
    proposal = more['pendingAction']['proposal']
    assert proposal['source'] == 'jwiz' and proposal['args']['quantity'] == 2 and proposal['args']['new_only']
    with session_scope() as db:
        assert db.scalar(select(Job).where(Job.created_by == account.id)) is None
    client = TestClient(app)
    payload = {'sessionId': sid, 'message': 'Yes, run the proposed scrape.', 'clientMessageId': 'action-click',
               'expectedProposalId': proposal['tool_call_id'], 'newOnly': False}
    response = client.post('/api/bot/chat', json=payload,
                           headers={'Authorization': 'Bearer ' + create_access_token(account)})
    assert response.status_code == 200, response.text
    approved = response.json()
    assert approved['jobId']
    assert client.post('/api/bot/chat', json=payload,
        headers={'Authorization': 'Bearer ' + create_access_token(account)}).json() == approved
    # The source repeats the original record before yielding two genuinely new ones.
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs:
                        iter(StandardRecord(**record(category, index)) for index in range(3)))
    worker.execute_job(approved['jobId'], 'action-test-worker')
    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(content='Here are 2 new matching contractors.'))
    complete = run_event_turn(sid, approved['jobId'])
    assert len(complete['records']) == 2
    assert first['records'][0]['id'] not in {row['id'] for row in complete['records']}
    with session_scope() as db:
        job = db.get(Job, approved['jobId'])
        assert job.status == 'Completed'
        assert db.scalar(select(Query).where(Query.id == complete['queryId'])).records_returned == 2


def test_full_details_followup_returns_same_record_without_substitution_or_scrape(account, monkeypatch):
    import importlib
    import agents.graph.runner as runner
    interpretation = importlib.import_module('agents.graph.nodes.gather_requirements')
    agent = importlib.import_module('agents.graph.nodes.agent')
    retrieval = importlib.import_module('agents.graph.nodes.rag_retrieve')
    category = 'general contractor-' + uuid.uuid4().hex
    with session_scope() as db:
        original = record(category, 0); original.update(website='https://details.example.test', notes='Original contractor details')
        saved = upsert_leads(db, [original, {**record(category, 1), 'phone': '+12125550101'}])
        from datetime import datetime, timezone, timedelta
        db.get(Lead, saved.lead_ids[0]).created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    def parse(schema, messages):
        payload = json.loads(messages[-1].content)
        if payload['latestMessage'] == 'get me everything about it in the db':
            assert payload['recentRecords'][0]['id'] == saved.lead_ids[0]
            return {'intent': 'records', 'is_followup': True, 'show_all_details': True,
                    'detail_record_ids': [saved.lead_ids[0]], 'criteria': {'has_email': True, 'has_phone': True}}
        return {'intent': 'records', 'criteria': dict(record_kind='company', category=category, city='New York',
            us_state='NY', location_scope='city', quantity=1, has_email=False, has_phone=False)}
    monkeypatch.setattr(interpretation, 'invoke_structured', parse)
    monkeypatch.setattr(retrieval.rag_client, 'status', lambda: {'state': 'not_deployed', 'available': False})
    monkeypatch.setattr(agent, 'get_chat_model', lambda **kwargs: object())
    def answer(model, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content='Here is the full stored record; the phone is not available.')
        return AIMessage(content='', tool_calls=[{'id': uuid.uuid4().hex, 'name': 'search_leads', 'args': {}}])
    monkeypatch.setattr(agent, 'invoke_llm', answer)
    graph = build_agent_graph(MemorySaver())
    monkeypatch.setattr(runner, 'get_compiled_graph', lambda: graph)
    sid = 'session-' + uuid.uuid4().hex
    initial = run_turn(account, sid, '1 general contractor in New York NY; neither contact required', 'initial')
    assert initial['records'][0]['id'] == saved.lead_ids[0]
    detail = run_turn(account, sid, 'get me everything about it in the db', 'details')
    assert detail['showAllDetails'] and len(detail['records']) == 1
    assert detail['records'][0]['id'] == initial['records'][0]['id']
    assert detail['records'][0]['phone'] is None
    assert detail['records'][0]['website'] == 'https://details.example.test'
    assert not detail['jobId'] and not detail['pendingAction']
    with session_scope() as db:
        trace = db.get(Query, detail['queryId']).parameters['trace']
        assert not any(entry.get('tool_name') == 'search_leads' for entry in trace)
        message = db.get(AgentMessage, detail['queryId']+':agent')
        assert message.message_metadata['showAllDetails']

@pytest.mark.parametrize('matching', [0, 1, 2])
@pytest.mark.parametrize('source_error', [False, True])
def test_recovery_dump_or_exact_matches_with_all_rows_saved(account, monkeypatch, matching, source_error):
    from Database.models.job import Job
    from Database.models.dataset import DatasetRecord
    from Database.models.session import AgentSession
    from services.jobs import enqueue_scrape
    from services.delivery import delivery_rows
    from scrappers.base import StandardRecord
    import worker
    import agents.graph.runner as runner
    tag = 'recovery-' + uuid.uuid4().hex
    rows = [StandardRecord(**{**record(tag, i), 'phone': '+12125550101'}) for i in range(matching)]
    rows += [StandardRecord(**record(tag, 10, city='Albany')),
             StandardRecord(**record(tag, 11, category='plumbing')),
             StandardRecord(**record(tag, 12))]  # Correct trade/location but missing required phone.
    # A repeat source row must not duplicate the database or displayed dump.
    rows += [rows[-1]]
    sid = 'session-' + uuid.uuid4().hex
    origin_id = str(uuid.uuid4())
    slots = {'record_kind': 'company', 'category': tag, 'city': 'New York', 'us_state': 'NY',
             'quantity': 2, 'has_email': True, 'has_phone': True, 'source': 'jwiz'}
    with session_scope() as db:
        db.add(AgentSession(id=sid, agent_id='agent-master', user_id=account.id, department_id='dept-default'))
        db.flush()
        db.add(Query(id=origin_id, user_id=account.id, session_id=sid, query_text='2 roofers in NYC with both contacts',
                     parameters={'slots': slots}))
        db.flush()
        job, _ = enqueue_scrape(db, user=account, script_id='jwiz', params={'limit': 2, 'city': 'New York',
                               'us_state': 'NY', 'keyword': tag}, query_id=origin_id)
        job_id = job.id
    def stream(*args, **kwargs):
        yield from rows
        if source_error:
            raise RuntimeError('Source interrupted after recovering records')
    monkeypatch.setattr(worker.controller, 'run', stream)
    worker.execute_job(job_id, 'recovery-test')
    with session_scope() as db:
        job = db.get(Job, job_id)
        assert job.status == ('Completed' if matching == 2 and not source_error else 'Partial')
        assert bool(job.error_message) == source_error
        assert db.query(DatasetRecord).filter_by(dataset_id=job.dataset_id).count() == matching + 3
        event = db.scalar(select(SessionEvent).where(SessionEvent.job_id == job_id))
        frozen = delivery_rows(db, event.query_id)
        assert len(frozen) == matching
        q = db.get(Query, event.query_id)
        assert q.parameters['matchingRecordsDelivered'] == matching
        assert q.parameters['requestFulfilled'] == (matching == 2)
        assert q.parameters['understoodRequest'] == slots
    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(content='The scrape has finished.'))
    completion = run_event_turn(sid, job_id)
    assert completion['records'] == frozen
    assert completion['requestTotalDelivered'] == matching  # Recovered rows never inflate fulfillment.
    assert completion['deliveryKind'] == ('matched' if matching == 2 else 'recovered')
    client = TestClient(app)
    with session_scope() as db:
        token = create_access_token(db.get(User, 'usr-env-admin'))
    headers = {'Authorization': 'Bearer ' + token}
    response = client.get('/api/admin/deliveries', params={'user_id': account.id}, headers=headers).json()
    delivery = next(d for d in response['groups'][0]['deliveries'] if d['queryId'] == completion['queryId'])
    assert delivery['records'] == frozen and delivery['understoodRequest'] == slots
    assert delivery['requestFulfilled'] == (matching == 2)
    import csv, io
    exported = client.get('/api/admin/deliveries/export.csv', params={'query_id': completion['queryId']}, headers=headers)
    csv_rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert csv_rows[0]['Request Fulfilled'] == str(matching == 2)
    assert csv_rows[0]['Delivery Kind'] == completion['deliveryKind']
    assert client.post('/api/bot/job-update', json={'sessionId': sid, 'jobId': job_id},
                       headers={'Authorization': 'Bearer ' + create_access_token(account)}).status_code == 200
    # Snapshots and outcome survive later updates to the live row.
    with session_scope() as db:
        db.get(Lead, frozen[0]['id']).category = 'changed-after-delivery'
        assert delivery_rows(db, completion['queryId']) == frozen
        metadata = db.get(AgentMessage, completion['queryId'] + ':agent').message_metadata
        assert metadata['requestFulfilled'] == (matching == 2)


def test_empty_scrape_has_explicit_error_and_visible_admin_completion(account, monkeypatch):
    from Database.models.job import Job
    from Database.models.session import AgentSession
    from services.jobs import enqueue_scrape
    import worker
    import agents.graph.runner as runner
    sid, qid = str(uuid.uuid4()), str(uuid.uuid4())
    slots = dict(record_kind='company', category='missing-' + uuid.uuid4().hex, city='New York', us_state='NY',
                 quantity=1, source='jwiz', has_email=True, has_phone=True)
    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master')); db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid, parameters={'slots': slots})); db.flush()
        job, _ = enqueue_scrape(db, user=account, script_id='jwiz', params={'limit': 1, 'us_state': 'NY'}, query_id=qid)
        jid = job.id
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter([]))
    worker.execute_job(jid, 'empty-recovery-test')
    with session_scope() as db:
        job = db.get(Job, jid)
        assert job.status == 'Failed' and 'no recoverable records' in job.error_message
    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(content='The request could not be fulfilled. No records were recovered.'))
    completion = run_event_turn(sid, jid)
    assert completion['records'] == [] and completion['requestFulfilled'] is False
    with session_scope() as db:
        token = create_access_token(db.get(User, 'usr-env-admin'))
    response = TestClient(app).get('/api/admin/deliveries', params={'user_id': account.id},
                                 headers={'Authorization': 'Bearer ' + token}).json()
    delivery = next(d for d in response['groups'][0]['deliveries'] if d['queryId'] == completion['queryId'])
    assert delivery['records'] == [] and delivery['matchingRecordsDelivered'] == 0
