"""
Unit and integration tests for sequential scraper fallback.
Covers:
1. Candidate scraper filtering & exclusion of attempted scrapers.
2. Shortfall / failure memory in prepare_completions (only on failure/shortfall).
3. LLM facts & event turn delivery with pendingAction and LangGraph interrupt.
4. Preserving attempted_scrapers across turns and never repeating attempted scrapers.
5. Announcing exhaustion when all category scrapers are exhausted.
"""
import json
import uuid
import pytest
from sqlalchemy import select

from Database.controller import session_scope
from Database.models.job import Job
from Database.models.query import Query
from Database.models.session import AgentSession
from Database.models.session_event import SessionEvent
from Database.models.user import User
from Database.search import SearchCriteria
from scrappers.base import StandardRecord
from services.jobs import enqueue_scrape
from services.completion import prepare_completions
from services.recovery_options import get_candidate_scrapers
from agents.graph.runner import run_event_turn, get_compiled_graph
from agents.graph.nodes.validate_proposal import validate_proposal
from agents.graph.nodes.enqueue_job import enqueue_job
from langchain_core.messages import AIMessage


@pytest.fixture
def account():
    with session_scope() as session:
        user = User(id='test-' + uuid.uuid4().hex, email='test-' + uuid.uuid4().hex + '@example.test',
                    name='Test user', role='user')
        session.add(user)
        return user


def test_get_candidate_scrapers_filtering_and_exclusion():
    """Verify get_candidate_scrapers filters by record_kind and excludes attempted scrapers."""
    slots = {'category': 'roofing', 'us_state': 'NY', 'city': 'New York', 'record_kind': 'company'}
    
    # Initially all company scrapers compatible with NY/New York are available
    all_candidates = get_candidate_scrapers(slots, attempted_scrapers=[])
    all_ids = [c['id'] for c in all_candidates]
    assert 'googlemaps' in all_ids
    assert 'bbb' in all_ids
    assert 'jwiz' in all_ids
    assert 'bluebook' in all_ids
    # Opportunity scrapers like dasny/bonfire must not be included
    assert 'dasny' not in all_ids
    assert 'bonfire' not in all_ids

    # Exclude googlemaps
    after_gm = get_candidate_scrapers(slots, attempted_scrapers=['googlemaps'])
    gm_ids = [c['id'] for c in after_gm]
    assert 'googlemaps' not in gm_ids
    assert 'bbb' in gm_ids

    # Exclude multiple
    after_multiple = get_candidate_scrapers(slots, attempted_scrapers=['googlemaps', 'bbb', 'jwiz'])
    mult_ids = [c['id'] for c in after_multiple]
    assert 'googlemaps' not in mult_ids
    assert 'bbb' not in mult_ids
    assert 'jwiz' not in mult_ids
    assert 'bluebook' in mult_ids

    # Exclude all company scrapers
    exhausted = get_candidate_scrapers(slots, attempted_scrapers=['googlemaps', 'bbb', 'jwiz', 'bluebook', 'houzz'])
    assert exhausted == []


def make_record(tag, index, source_code='googlemaps'):
    return {
        'source_code': source_code,
        'record_kind': 'company',
        'external_id': f'{tag}-{index}',
        'organization_name': f'Roofer {tag} {index}',
        'category': tag,
        'city': 'New York',
        'us_state': 'NY',
        'email': f'{tag}-{index}@example.test',
        'source_url': f'https://example.test/{tag}/{index}',
    }


def test_prepare_completions_fulfilled_vs_unfulfilled(account, monkeypatch):
    """Verify fallback memory is passed ONLY when unfulfilled, not when fulfilled."""
    import worker
    sid = 'session-' + uuid.uuid4().hex
    qid = str(uuid.uuid4())
    tag = 'roofing-' + uuid.uuid4().hex
    slots = {'category': tag, 'us_state': 'NY', 'city': 'New York', 'quantity': 5, 'record_kind': 'company',
             'has_email': False, 'has_phone': False}

    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid, parameters={'slots': slots, 'attempted_scrapers': []}))
        db.flush()
        job, _ = enqueue_scrape(db, user=account, script_id='googlemaps',
                                params={'limit': 5, 'keyword': tag, 'us_state': 'NY', 'city': 'New York'},
                                query_id=qid)
        jid = job.id

    # 1. Unfulfilled case (only 2 records returned out of 5 requested)
    rows_partial = [
        StandardRecord(**make_record(tag, i))
        for i in range(2)
    ]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows_partial))
    worker.execute_job(jid, 'partial-worker')

    with session_scope() as db:
        event = db.scalar(select(SessionEvent).where(SessionEvent.job_id == jid))
        event_q = db.get(Query, event.query_id)
        assert event_q.parameters['requestFulfilled'] is False
        assert event_q.parameters['matchingRecordsDelivered'] == 2
        assert event_q.parameters['requestedRecords'] == 5
        assert event_q.parameters['remaining_records'] == 3
        assert 'googlemaps' in event_q.parameters['attempted_scrapers']
        # Candidates must NOT include googlemaps
        candidate_ids = [c['id'] for c in event_q.parameters['candidate_scrapers']]
        assert 'googlemaps' not in candidate_ids
        assert event_q.parameters['recommended_scraper'] is not None
        db.get(AgentSession, sid).status = 'archived'

    # 2. Fulfilled case (target reached)
    sid2 = 'session-' + uuid.uuid4().hex
    qid2 = str(uuid.uuid4())
    tag2 = 'roofing-' + uuid.uuid4().hex
    slots2 = {'category': tag2, 'us_state': 'NY', 'city': 'New York', 'quantity': 5, 'record_kind': 'company',
              'has_email': False, 'has_phone': False}
    with session_scope() as db:
        db.add(AgentSession(id=sid2, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid2, user_id=account.id, session_id=sid2, parameters={'slots': slots2, 'attempted_scrapers': []}))
        db.flush()
        job2, _ = enqueue_scrape(db, user=account, script_id='googlemaps',
                                 params={'limit': 5, 'keyword': tag2, 'us_state': 'NY', 'city': 'New York'},
                                 query_id=qid2)
        jid2 = job2.id

    rows_full = [
        StandardRecord(**make_record(tag2, i))
        for i in range(5)
    ]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows_full))
    worker.execute_job(jid2, 'full-worker')

    with session_scope() as db:
        event2 = db.scalar(select(SessionEvent).where(SessionEvent.job_id == jid2))
        event_q2 = db.get(Query, event2.query_id)
        assert event_q2.parameters['requestFulfilled'] is True
        # Fallback memory must be None when fulfilled
        assert event_q2.parameters.get('candidate_scrapers') is None
        assert event_q2.parameters.get('candidateScrapers') is None
        assert event_q2.parameters.get('remaining_records') is None


def test_validate_proposal_rejects_already_attempted_scraper():
    """Verify validate_proposal refuses a proposal for an already attempted scraper."""
    criteria_slots = {'category': 'roofing', 'us_state': 'NY', 'city': 'New York', 'quantity': 10,
                      'record_kind': 'company', 'has_email': False, 'has_phone': False}
    criteria = SearchCriteria.from_slots(criteria_slots)
    
    state = {
        'request_intent': 'records',
        'turn_id': 'turn-1',
        'query_id': 'q-1',
        'slots': criteria_slots,
        'attempted_scrapers': ['googlemaps'],
        'last_search': {
            'turn_id': 'turn-1',
            'slots_hash': criteria.fingerprint(),
            'total': 0,
            'sufficient': False,
            'error': False,
        },
        'messages': [AIMessage(content='', tool_calls=[{
            'id': 'call-1',
            'name': 'propose_scrape',
            'args': {'source': 'googlemaps', 'quantity': 10},
        }])],
    }

    result = validate_proposal(state)
    assert result['pending_proposal'] is None
    refusal_msg = result['messages'][0].content
    assert 'already been attempted' in refusal_msg


def test_enqueue_job_accumulates_attempted_scrapers(account):
    """Verify enqueue_job accumulates the current source into attempted_scrapers."""
    criteria_slots = {'category': 'roofing', 'us_state': 'NY', 'city': 'New York', 'quantity': 10,
                      'record_kind': 'company', 'has_email': False, 'has_phone': False}
    criteria = SearchCriteria.from_slots(criteria_slots)
    qid = str(uuid.uuid4())
    sid = str(uuid.uuid4())

    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid, parameters={'slots': criteria_slots}))
        db.flush()

    state = {
        'user_id': account.id,
        'session_id': sid,
        'query_id': qid,
        'turn_id': 'turn-1',
        'confirmed': True,
        'request_intent': 'records',
        'slots': criteria_slots,
        'attempted_scrapers': ['googlemaps'],
        'last_search': {
            'turn_id': 'turn-1',
            'slots_hash': criteria.fingerprint(),
            'total': 0,
            'sufficient': False,
            'error': False,
        },
        'pending_proposal': {
            'id': 'prop-1',
            'query_id': qid,
            'source': 'bbb',
            'args': {'source': 'bbb', 'quantity': 10, 'category': 'roofing', 'us_state': 'NY', 'city': 'New York',
                     'attempted_scrapers': ['googlemaps']},
            'criteria_hash': criteria.fingerprint(),
            'tool_call_id': 'call-1',
        },
    }

    result = enqueue_job(state)
    assert result['active_job_id'] is not None
    assert 'googlemaps' in result['attempted_scrapers']
    assert 'bbb' in result['attempted_scrapers']
    with session_scope() as db:
        q = db.get(Query, qid)
        assert q.parameters['attempted_scrapers'] == ['googlemaps', 'bbb']


def test_run_event_turn_shortfall_creates_proposal_and_interrupt(account, monkeypatch):
    """Verify that when a scrape falls short, run_event_turn attaches pendingAction and pauses graph."""
    import worker
    import agents.graph.runner as runner
    sid = 'session-' + uuid.uuid4().hex
    qid = str(uuid.uuid4())
    tag = 'roofing-' + uuid.uuid4().hex
    slots = {'category': tag, 'us_state': 'NY', 'city': 'New York', 'quantity': 10, 'record_kind': 'company',
             'has_email': False, 'has_phone': False}

    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid, parameters={'slots': slots, 'attempted_scrapers': []}))
        db.flush()
        job, _ = enqueue_scrape(db, user=account, script_id='googlemaps',
                                params={'limit': 10, 'keyword': tag, 'us_state': 'NY', 'city': 'New York'},
                                query_id=qid)
        jid = job.id

    # Returns only 3 records (shortfall of 7)
    rows = [
        StandardRecord(**make_record(tag, i))
        for i in range(3)
    ]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows))
    worker.execute_job(jid, 'shortfall-test-worker')

    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='Google Maps returned 3 of 10 requested roofers. Would you like to run BBB for the remaining 7 records?'
    ))

    completion = run_event_turn(sid, jid)
    assert completion['requestFulfilled'] is False
    assert completion['matchingRecordsDelivered'] == 3
    assert completion['remaining_records'] == 7
    assert 'googlemaps' in completion['attempted_scrapers']
    assert completion['pendingAction'] is not None
    assert completion['pendingAction']['type'] == 'scrape_confirmation'
    proposal = completion['pendingAction']['proposal']
    assert proposal['source'] != 'googlemaps'
    assert proposal['args']['quantity'] == 7
    assert 'googlemaps' in proposal['args']['attempted_scrapers']

    # Check that the LangGraph snapshot has an interrupt waiting
    graph = get_compiled_graph()
    snap = graph.get_state({'configurable': {'thread_id': sid}})
    assert snap.interrupts
    interrupt_val = snap.interrupts[0].value
    assert interrupt_val['proposal']['source'] == proposal['source']
    assert interrupt_val['proposal']['tool_call_id'] == proposal['tool_call_id']


def test_exhaustion_when_all_category_scrapers_attempted(account, monkeypatch):
    """Verify that when all category scrapers are in attempted_scrapers, candidates is empty and no proposal is made."""
    import worker
    import agents.graph.runner as runner
    sid = 'session-' + uuid.uuid4().hex
    qid = str(uuid.uuid4())
    tag = 'roofing-' + uuid.uuid4().hex
    # Pre-populate all other company scrapers into attempted_scrapers
    all_other_company_scrapers = ['bbb', 'bluebook', 'houzz', 'jwiz']
    slots = {'category': tag, 'us_state': 'NY', 'city': 'New York', 'quantity': 10, 'record_kind': 'company',
             'has_email': False, 'has_phone': False}

    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid,
                     parameters={'slots': slots, 'attempted_scrapers': all_other_company_scrapers}))
        db.flush()
        job, _ = enqueue_scrape(db, user=account, script_id='googlemaps',
                                params={'limit': 10, 'keyword': tag, 'us_state': 'NY', 'city': 'New York'},
                                query_id=qid)
        jid = job.id

    rows = [
        StandardRecord(**make_record(tag, i))
        for i in range(2)
    ]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows))
    worker.execute_job(jid, 'exhaustion-worker')

    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='Google Maps returned 2 of 10 requested roofers. All available scrapers for this category have been exhausted.'
    ))

    completion = run_event_turn(sid, jid)
    assert completion['requestFulfilled'] is False
    assert completion['candidate_scrapers'] == []
    assert completion['recommended_scraper'] is None
    # No proposal should be created since all scrapers are exhausted
    assert completion['pendingAction'] is None
    assert completion['proposedActions'] == []


def test_fallback_job_confirmation_and_chaining(account, monkeypatch):
    """Verify that when a user approves a fallback proposal, the fallback job executes,
    delivers records, prepares completion, and fulfills the request or chains next candidate."""
    import worker
    import agents.graph.runner as runner
    sid = 'session-' + uuid.uuid4().hex
    qid = str(uuid.uuid4())
    tag = 'roofing-' + uuid.uuid4().hex
    slots = {'category': tag, 'us_state': 'NY', 'city': 'New York', 'quantity': 5, 'record_kind': 'company',
             'has_email': False, 'has_phone': False}

    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid, parameters={'slots': slots, 'attempted_scrapers': []}))
        db.flush()
        job1, _ = enqueue_scrape(db, user=account, script_id='googlemaps',
                                 params={'limit': 5, 'keyword': tag, 'us_state': 'NY', 'city': 'New York'},
                                 query_id=qid)
        j1_id = job1.id

    # 1. Job 1 returns 2 of 5 requested records
    rows1 = [StandardRecord(**make_record(tag, i, 'googlemaps')) for i in range(2)]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows1))
    worker.execute_job(j1_id, 'worker-1')

    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='Google Maps returned 2 of 5 roofers. Would you like to run BBB for the remaining 3 records?'
    ))
    completion1 = run_event_turn(sid, j1_id)
    assert completion1['requestFulfilled'] is False
    assert completion1['pendingAction'] is not None
    proposal = completion1['pendingAction']['proposal']
    tool_call_id = proposal['tool_call_id']
    next_source = proposal['source']
    assert next_source == 'bbb'

    # 2. User confirms the fallback proposal via run_turn
    monkeypatch.setattr(runner, 'classify_confirmation', lambda text, pending: {'decision': 'approve', 'text': text})

    turn2_res = runner.run_turn(account, sid, 'Yes, run the proposed scrape.', expected_proposal_id=tool_call_id)
    j2_id = turn2_res.get('jobId')
    assert j2_id is not None, f"Expected jobId in response, got: {turn2_res}"

    # 3. Fallback job 2 runs and delivers the remaining 3 records (fulfilling the 5 total target)
    rows2 = [StandardRecord(**make_record(tag, 2 + i, next_source)) for i in range(3)]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows2))
    worker.execute_job(j2_id, 'worker-2')

    with session_scope() as db:
        events2 = db.scalars(select(SessionEvent).where(SessionEvent.job_id == j2_id)).all()
        assert len(events2) > 0, f"Expected SessionEvent for fallback job {j2_id}, but found none!"

    # 4. Completion 2 is delivered to the user with request fulfilled!
    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='BBB returned 3 records. All 5 requested roofers have been delivered.'
    ))
    completion2 = run_event_turn(sid, j2_id)
    assert completion2['requestFulfilled'] is True
    assert completion2['matchingRecordsDelivered'] == 5
    assert len(completion2['records']) == 5
    assert completion2['pendingAction'] is None
    assert completion2['candidate_scrapers'] is None


def test_multi_tier_sequential_fallback_chaining(account, monkeypatch):
    """Verify 3-tier sequential chaining: googlemaps (1/5) -> bbb (2/4) -> 3rd scraper (2/2) fulfills request."""
    import worker
    import agents.graph.runner as runner
    sid = 'session-' + uuid.uuid4().hex
    qid = str(uuid.uuid4())
    tag = 'roofing-' + uuid.uuid4().hex
    slots = {'category': tag, 'us_state': 'NY', 'city': 'New York', 'quantity': 5, 'record_kind': 'company',
             'has_email': False, 'has_phone': False}

    with session_scope() as db:
        db.add(AgentSession(id=sid, user_id=account.id, department_id='dept-default', agent_id='agent-master'))
        db.flush()
        db.add(Query(id=qid, user_id=account.id, session_id=sid, parameters={'slots': slots, 'attempted_scrapers': []}))
        db.flush()
        job1, _ = enqueue_scrape(db, user=account, script_id='googlemaps',
                                 params={'limit': 5, 'keyword': tag, 'us_state': 'NY', 'city': 'New York'},
                                 query_id=qid)
        j1_id = job1.id

    # 1. Job 1 (googlemaps) returns 1 of 5 records
    rows1 = [StandardRecord(**make_record(tag, 0, 'googlemaps'))]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows1))
    worker.execute_job(j1_id, 'worker-1')

    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='Google Maps returned 1 of 5 roofers. Would you like to run BBB for the remaining 4 records?'
    ))
    c1 = run_event_turn(sid, j1_id)
    assert c1['requestFulfilled'] is False
    assert c1['matchingRecordsDelivered'] == 1
    assert c1['pendingAction'] is not None
    prop1 = c1['pendingAction']['proposal']
    assert prop1['source'] == 'bbb'
    assert 'googlemaps' in prop1['args']['attempted_scrapers']

    # 2. User confirms proposal 1 -> Job 2 (bbb)
    monkeypatch.setattr(runner, 'classify_confirmation', lambda text, pending: {'decision': 'approve', 'text': text})
    turn2 = runner.run_turn(account, sid, 'Yes, run BBB.', expected_proposal_id=prop1['tool_call_id'])
    j2_id = turn2.get('jobId')
    assert j2_id is not None

    # 3. Job 2 (bbb) returns 2 more records (total 3 of 5)
    rows2 = [StandardRecord(**make_record(tag, 1, 'bbb')), StandardRecord(**make_record(tag, 2, 'bbb'))]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows2))
    worker.execute_job(j2_id, 'worker-2')

    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='BBB returned 2 of 4 remaining roofers (3 of 5 total). Would you like to run the next scraper for the remaining 2?'
    ))
    c2 = run_event_turn(sid, j2_id)
    assert c2['requestFulfilled'] is False
    assert c2['matchingRecordsDelivered'] == 3
    assert c2['pendingAction'] is not None
    prop2 = c2['pendingAction']['proposal']
    src3 = prop2['source']
    # Must NOT be googlemaps or bbb
    assert src3 not in ('googlemaps', 'bbb')
    assert set(prop2['args']['attempted_scrapers']) >= {'googlemaps', 'bbb'}
    assert prop2['args']['quantity'] == 2

    # 4. User confirms proposal 2 -> Job 3
    turn3 = runner.run_turn(account, sid, 'Yes, run the next scraper.', expected_proposal_id=prop2['tool_call_id'])
    j3_id = turn3.get('jobId')
    assert j3_id is not None

    # 5. Job 3 delivers the remaining 2 records (total 5 of 5)
    rows3 = [StandardRecord(**make_record(tag, 3, src3)), StandardRecord(**make_record(tag, 4, src3))]
    monkeypatch.setattr(worker.controller, 'run', lambda *args, **kwargs: iter(rows3))
    worker.execute_job(j3_id, 'worker-3')

    monkeypatch.setattr(runner, 'invoke_llm', lambda *args, **kwargs: AIMessage(
        content='Scraper returned 2 records. All 5 requested roofers have been delivered.'
    ))
    c3 = run_event_turn(sid, j3_id)
    assert c3['requestFulfilled'] is True
    assert c3['matchingRecordsDelivered'] == 5
    assert len(c3['records']) == 5
    assert c3['pendingAction'] is None
    assert c3['candidate_scrapers'] is None

