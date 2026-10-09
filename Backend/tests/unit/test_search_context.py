from unittest.mock import MagicMock

from agents.graph.tools.search import search_leads


def test_new_request_can_clear_old_filters_while_followups_keep_them(monkeypatch):
    import Database.controller as database
    context = MagicMock()
    repo = MagicMock()
    repo.leads.search_leads.return_value = ([], 0)
    monkeypatch.setattr(database, 'session_scope', lambda: context)
    monkeypatch.setattr(database, 'Repositories', lambda _: repo)
    state = {'slots': {'category': 'roofing', 'city': 'Yonkers', 'us_state': 'NY',
        'record_kind': 'company', 'source': 'jwiz', 'has_email': True}, 'turn_id': 'new-request'}
    response = search_leads.func(source='dasny', quantity=2, record_kind='opportunity', us_state='NY',
        reset_filters=True, state=state, tool_call_id='new-search')
    slots = response.update['slots']
    assert slots['category'] is None and slots['city'] is None and not slots['has_email']
    assert slots['source'] == 'dasny' and slots['record_kind'] == 'opportunity'
    followup = search_leads.func(quantity=5, state=state, tool_call_id='followup-search')
    assert followup.update['slots']['city'] == 'Yonkers'
    assert followup.update['slots']['category'] == 'roofing'
    assert followup.update['slots']['has_email']


def test_current_request_criteria_override_incompatible_old_tool_arguments(monkeypatch):
    import Database.controller as database
    repo = MagicMock(); repo.leads.search_leads.return_value = ([], 0)
    monkeypatch.setattr(database, 'session_scope', lambda: MagicMock())
    monkeypatch.setattr(database, 'Repositories', lambda _: repo)
    state = {'request_intent': 'records', 'slots': {'category': None, 'city': None,
        'us_state': 'NY', 'quantity': 2, 'source': 'dasny', 'record_kind': 'opportunity',
        'category_specified': True, 'location_scope': 'statewide', 'has_email': False, 'has_phone': False}}
    response = search_leads.func(category='roofing', city='Yonkers', quantity=10,
        state=state, tool_call_id='search')
    assert response.update['slots']['city'] is None
    assert response.update['slots']['category'] is None
    assert response.update['slots']['quantity'] == 2
    assert repo.leads.search_leads.call_args.kwargs['city'] is None


def test_missing_quantity_asks_before_database_search(monkeypatch):
    import Database.controller as database
    connection = MagicMock()
    monkeypatch.setattr(database, 'session_scope', connection)
    response = search_leads.func(quantity=20, state={'request_intent': 'records',
        'slots': {'quantity': None}}, tool_call_id='search')
    assert 'quantity' in response.update['messages'][0].content
    connection.assert_not_called()


def test_interpretation_retains_explicitly_cleared_fields(monkeypatch):
    from agents.graph.nodes import gather_requirements as module
    monkeypatch.setattr(module, 'invoke_structured', lambda *a: {'intent': 'records',
        'criteria': {'record_kind': 'opportunity', 'source': 'dasny', 'quantity': 2,
            'us_state': 'New York', 'city': None, 'category': None}})
    result = module.interpret_request({'user_text': 'Two DASNY bids, statewide',
        'slots': {'city': 'Yonkers', 'category': 'roofing', 'has_email': True}})
    assert result['slots']['city'] is None and result['slots']['category'] is None
    assert result['slots']['us_state'] == 'NY' and result['slots']['has_email'] is None
    assert result['missing_requirements'] and not result['requirements_met']


def test_greeting_is_model_written_with_requirements_and_without_tools(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage
    from agents.graph.nodes import agent, gather_requirements
    from agents.graph.persist import _compute_decision
    calls = []
    model = object()
    monkeypatch.setattr(gather_requirements, 'interpret_request', lambda _: {'request_intent': 'greeting'})
    def get_model(**kwargs):
        calls.append(kwargs)
        return model
    monkeypatch.setattr(agent, 'get_chat_model', get_model)
    reply = AIMessage(content='Hello! Please share your trade, state, quantity, record type, and contact requirements.')
    def invoke(actual_model, messages):
        assert actual_model is model
        prompt = messages[0].content
        assert 'Current Message: Greeting' in prompt
        for requirement in ('record type', 'trade/category', 'location (state, or statewide)', 'number of records', 'required contact fields'):
            assert requirement in prompt
        assert 'capabilities menu' in prompt
        return reply
    monkeypatch.setattr(agent, 'invoke_llm', invoke)
    state = {'user_text': 'hello', 'messages': [HumanMessage(content='hello')], 'tool_steps': 0,
        'trace': [{'tool': 'rag_retrieve', 'state': 'not_deployed'}]}
    result = agent.call_model(state)
    assert calls == [{}]
    assert result['messages'] == [reply]
    assert result['decision'] == 'NONE'
    assert _compute_decision({**state, **result}) == 'NONE'


def test_each_required_field_blocks_search_until_supplied(monkeypatch):
    from agents.graph.nodes.gather_requirements import missing_requirements
    from agents.graph.tools.search import count_leads
    import Database.controller as database
    complete = dict(record_kind='company', category='roofing', city='New York', us_state='NY',
        quantity=1, has_email=False, has_phone=False)
    assert missing_requirements(complete) == []
    assert missing_requirements({**complete, 'city': None}) == []
    database_access = MagicMock(side_effect=AssertionError('Incomplete criteria must not search'))
    monkeypatch.setattr(database, 'session_scope', database_access)
    for field in ['record_kind', 'category', 'us_state', 'quantity', 'has_email', 'has_phone']:
        slots = {**complete, field: None}
        assert missing_requirements(slots), field
        state = {'request_intent': 'records', 'slots': slots}
        blocked = search_leads.func(state=state, tool_call_id='blocked')
        assert blocked.update['decision'] == 'CLARIFY'
        assert count_leads.func(state=state)['error'] == 'Requirements incomplete'
    database_access.assert_not_called()


def test_explicit_any_and_neither_are_complete_without_silent_defaults():
    from agents.graph.nodes.gather_requirements import missing_requirements
    criteria = dict(record_kind='opportunity', category=None, category_specified=True,
        location_scope='statewide', us_state='NY', quantity=2, has_email=False, has_phone=False)
    assert missing_requirements(criteria) == []
    assert missing_requirements({**criteria, 'category_specified': False})
    assert missing_requirements({**criteria, 'us_state': None})
    assert missing_requirements({**criteria, 'location_scope': None}) == []
    assert missing_requirements({**criteria, 'has_email': None})
    assert missing_requirements({**criteria, 'location_scope': 'any', 'us_state': None}) == []


def test_incomplete_request_has_no_bound_tools_and_no_rag_lookup(monkeypatch):
    from agents.graph.nodes import agent
    from agents.graph.nodes.rag_retrieve import rag_retrieve
    from langchain_core.messages import AIMessage, HumanMessage
    import importlib
    retrieval = importlib.import_module('agents.graph.nodes.rag_retrieve')
    forbidden = MagicMock(side_effect=AssertionError('No KB access before requirements'))
    monkeypatch.setattr(retrieval.rag_client, 'status', forbidden)
    state = {'request_intent': 'records', 'intent_interpreted': True, 'requirements_met': False,
        'slots': {'record_kind': 'company', 'category': 'roofing', 'quantity': 1},
        'messages': [HumanMessage(content='1 roofing contractor')], 'tool_steps': 0}
    assert rag_retrieve(state)['rag_status']['state'] == 'not_checked'
    calls = []
    monkeypatch.setattr(agent, 'get_chat_model', lambda **kwargs: calls.append(kwargs) or object())
    def reply(model, messages):
        assert 'Requirements Incomplete' in messages[0].content
        return AIMessage(content='Which city and state, and do you need email, phone, both, or neither?')
    monkeypatch.setattr(agent, 'invoke_llm', reply)
    result = agent.call_model(state)
    assert calls == [{}] and result['decision'] == 'CLARIFY'
    assert not result['requirements_met']
    forbidden.assert_not_called()


def test_approved_incomplete_proposal_cannot_enqueue(monkeypatch):
    import importlib
    enqueue = importlib.import_module('agents.graph.nodes.enqueue_job')
    forbidden = MagicMock(side_effect=AssertionError('No job before requirements'))
    monkeypatch.setattr(enqueue, 'enqueue_scrape', forbidden)
    result = enqueue.enqueue_job({'request_intent': 'records', 'confirmed': True,
        'slots': {'record_kind': 'company', 'category': 'roofing', 'quantity': 1},
        'pending_proposal': {'tool_call_id': 'old-proposal'}})
    assert result['decision'] == 'CLARIFY' and not result['confirmed']
    assert result['pending_proposal'] is None
    forbidden.assert_not_called()


def test_clarification_merges_only_supplied_answers_and_new_requests_reset(monkeypatch):
    from agents.graph.nodes import gather_requirements as module
    pending = dict(record_kind='company', category='roofing', quantity=1,
                   city=None, us_state=None, has_email=None, has_phone=None)
    def extract_location(schema, messages):
        assert 'previousCriteria' not in messages[-1].content
        assert 'awaitingRequirements' in messages[-1].content
        return {'intent': 'records', 'is_followup': True,
                'criteria': {'city': 'New York', 'us_state': 'NY', 'location_scope': 'city'}}
    monkeypatch.setattr(module, 'invoke_structured', extract_location)
    location = module.interpret_request({'user_text': 'New York city, NY', 'slots': pending,
                                        'missing_requirements': module.missing_requirements(pending)})
    assert location['slots']['category'] == 'roofing' and location['slots']['quantity'] == 1
    assert len(location['missing_requirements']) == 1 and not location['requirements_met']
    monkeypatch.setattr(module, 'invoke_structured', lambda *args: {'intent': 'records',
        'is_followup': True, 'criteria': {'has_email': False, 'has_phone': False}})
    complete = module.interpret_request({**location, 'user_text': 'Neither'})
    assert complete['requirements_met'] and complete['slots']['city'] == 'New York'
    monkeypatch.setattr(module, 'invoke_structured', lambda *args: {'intent': 'records',
        'is_followup': False, 'criteria': {'record_kind': 'company', 'category': 'plumbing', 'quantity': 2}})
    fresh = module.interpret_request({**complete, 'user_text': '2 plumbing contractors'})
    assert fresh['slots']['city'] is None and fresh['slots']['has_email'] is None
    assert not fresh['requirements_met'] and len(fresh['missing_requirements']) == 2


def test_clarification_does_not_replay_tool_protocol_history(monkeypatch):
    from agents.graph.nodes import agent
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    monkeypatch.setattr(agent, 'get_chat_model', lambda **kwargs: object())
    def reply(model, messages):
        assert not any(isinstance(message, ToolMessage) or getattr(message, 'tool_calls', None) for message in messages)
        assert len(messages) == 2 and messages[-1].content == '2 plumbing contractors'
        assert 'Database Before Scrape' not in messages[0].content
        return AIMessage(content='Which location and contact requirements?')
    monkeypatch.setattr(agent, 'invoke_llm', reply)
    result = agent.call_model({'request_intent': 'records', 'intent_interpreted': True,
        'slots': {'record_kind': 'company', 'category': 'plumbing', 'quantity': 2},
        'messages': [HumanMessage(content='Previous roofing search'),
            AIMessage(content='', tool_calls=[{'id': 'old', 'name': 'search_leads', 'args': {}}]),
            ToolMessage(content='Found one', tool_call_id='old'), HumanMessage(content='2 plumbing contractors')]})
    assert result['decision'] == 'CLARIFY'


def test_everything_uses_context_contacts_and_validated_record_reference(monkeypatch):
    from agents.graph.nodes import gather_requirements as module
    import json
    previous = dict(record_kind='company', category='general contractor', city='New York', us_state='NY',
                    quantity=1, has_email=False, has_phone=False)
    def parse(schema, messages):
        payload = json.loads(messages[-1].content)
        assert payload['recentRecords'][0]['company'] == 'The returned contractor'
        return {'intent': 'records', 'is_followup': True, 'show_all_details': True,
                'detail_record_ids': ['returned-id'], 'criteria': {'has_email': True, 'has_phone': True}}
    monkeypatch.setattr(module, 'invoke_structured', parse)
    state = dict(user_text='get me everything about it in the db', slots=previous,
                 recent_records=[dict(id='returned-id', company='The returned contractor')])
    result = module.interpret_request(state)
    assert result['requirements_met'] and result['slots']['quantity'] == 1
    assert result['slots']['has_email'] and result['slots']['has_phone'] and result['slots']['show_all_details']
    assert result['slots']['detail_record_ids'] == ['returned-id']
    monkeypatch.setattr(module, 'invoke_structured', lambda *args: {'intent': 'records', 'is_followup': True,
        'show_all_details': True, 'detail_record_ids': ['invented-id'], 'criteria': {'has_email': True, 'has_phone': True}})
    invalid = module.interpret_request(state)
    assert not invalid['requirements_met'] and invalid['slots']['detail_record_ids'] == []
    assert 'which previously returned' in invalid['missing_requirements'][0]
