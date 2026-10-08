"""Validate same-request search evidence and source capabilities before consent."""
import hashlib
import json
from langchain_core.messages import ToolMessage
from Database.search import SearchCriteria
from scrappers.controller import check_ready, get_meta, validate_params


def validate_proposal(state):
    calls = getattr((state.get('messages') or [None])[-1], 'tool_calls', None) or []
    call = next((c for c in calls if c['name'] == 'propose_scrape'), None)
    if not call:
        return {}
    args = call.get('args') or {}
    evidence = state.get('last_search') or {}
    criteria = SearchCriteria.from_slots(state.get('slots'))
    error = None
    source = (args.get('source') or '').lower()
    try:
        from agents.graph.nodes.gather_requirements import missing_requirements
        if state.get('request_intent') == 'records' and missing_requirements(state.get('slots')):
            raise ValueError('All required criteria must be supplied before a scrape proposal')
        if not evidence or evidence.get('error'):
            raise ValueError('A successful database search is required before a proposal')
        if evidence.get('turn_id') != state.get('turn_id') or evidence.get('slots_hash') != criteria.fingerprint():
            raise ValueError('Search the same criteria in this turn before proposing a scrape')
        if evidence.get('sufficient'):
            raise ValueError('The database already contains enough matching records')
        meta = get_meta(source)
        ready, reason = check_ready(source)
        if not ready:
            raise ValueError('Source is not ready: ' + str(reason))
        if criteria.record_kind and meta.record_kind != criteria.record_kind:
            raise ValueError('Source supplies the wrong record type')
        for field in ['category', 'city', 'us_state']:
            if args.get(field) and SearchCriteria.from_slots({**criteria.model_dump(), field: args[field]}).model_dump()[field] != criteria.model_dump()[field]:
                raise ValueError('Proposal criteria differ from the searched request')
        missing = max(1, criteria.quantity - evidence.get('total', 0))
        quantity = min(args.get('quantity') or missing, missing)
        params = validate_params(source, {'limit': quantity, 'keyword': criteria.category,
            'city': criteria.city, 'us_state': criteria.us_state})
        normalized = {**criteria.model_dump(), 'source': source, 'quantity': params.limit}
        seed = str(state.get('query_id')) + json.dumps(normalized, sort_keys=True)
        proposal = {'id': hashlib.sha256(seed.encode()).hexdigest(), 'query_id': state.get('query_id'), 'source': source,
            'args': normalized, 'criteria_hash': criteria.fingerprint(), 'tool_call_id': call['id'], 'question': ''}
    except Exception as exc:
        error = str(exc)
    other = [ToolMessage(content='Call propose_scrape alone.', tool_call_id=c['id']) for c in calls if c is not call]
    if error:
        return {'pending_proposal': None, 'messages': [ToolMessage(content='Proposal refused: ' + error, tool_call_id=call['id']), *other]}
    return {'pending_proposal': proposal, 'confirmed': False, 'messages': other}
