"""Durable turns, ordered tool traces and immutable delivered result snapshots."""
from datetime import datetime, timezone
from Database.controller import session_scope, Repositories
from Database.models.query import Query
from Database.models.message import AgentMessage
from services.delivery import record_delivery
from agents.graph.utils import normalize_content


def _compute_decision(state):
    if state.get('decision'):
        return state['decision']
    if (state.get('last_search') or {}).get('sufficient'):
        return 'DB'
    if state.get('rag_hits') and not state.get('last_search'):
        return 'KB'
    return 'CLARIFY' if state.get('trace') else 'NONE'


def _persist(state, paused=False):
    query_id = state.get('query_id')
    if not query_id:
        return
    with session_scope() as session:
        q = session.get(Query, query_id)
        if not q:
            return
        from services.sessions import require_active
        require_active(q.session_id, session)
        search = state.get('last_search') or {}
        records = list(search.get('items') or [])
        seen = {r['id'] for r in records}
        from routes.serializers import serialize_lead
        for lid in state.get('served_lead_ids') or []:
            if lid not in seen:
                lead = Repositories(session).leads.get_by_id(lid)
                if lead:
                    records.append(serialize_lead(lead)); seen.add(lid)
        records = record_delivery(session, q, records)
        messages = state.get('messages') or []
        reply = (state.get('pending_proposal') or {}).get('question') if paused else None
        if not reply:
            reply = next((normalize_content(m.content) for m in reversed(messages) if getattr(m, 'type', '') == 'ai' and not getattr(m, 'tool_calls', None)), '')
        q.parameters = {**(q.parameters or {}), 'slots': state.get('slots') or {},
            'kb_state': (state.get('rag_status') or {}).get('state'),
            'kb_hit_ids': [h.get('chunkId') for h in state.get('rag_hits') or []], 'trace': state.get('trace') or []}
        q.decision = _compute_decision(state)
        q.status = 'awaiting_confirmation' if paused else 'completed'
        q.job_id = state.get('active_job_id') or q.job_id
        q.response = {'reply': reply, 'records': records, 'total': len(records),
            'showAllDetails': bool((state.get('slots') or {}).get('show_all_details')),
            'missingRequirements': state.get('missing_requirements') or [],
            'totalAvailable': search.get('total', len(records)), 'queryId': q.id,
            'jobId': q.job_id, 'decision': q.decision, 'sessionId': q.session_id,
            'pendingAction': {'type': 'scrape_confirmation', 'proposal': state.get('pending_proposal'), 'question': reply} if paused else None,
            'kb': {'state': (state.get('rag_status') or {}).get('state'), 'available': bool((state.get('rag_status') or {}).get('available')), 'hits': state.get('rag_hits') or []}}
        slots = state.get('slots') or {}
        proposal = state.get('pending_proposal') or {}
        q.response = {**q.response, 'proposedActions': [{'actionType': 'scrape', 'label': reply,
            'parameters': proposal.get('args') or {}, 'requiresConfirmation': True}] if paused else [],
            'suggestions': [], 'updatedRequirement': {'industry': slots.get('category'),
                'location': ', '.join(v for v in [slots.get('city'), slots.get('us_state')] if v),
                'quantity': slots.get('quantity'), 'status': 'scraping' if q.job_id else 'collecting',
                'completionPercentage': min(100, int(len(records) * 100 / max(1, slots.get('quantity') or 1)))}}
        if q.session_id:
            transcript = []
            for message in reversed(messages):
                transcript.append({'type': getattr(message, 'type', ''), 'content': normalize_content(message.content),
                    'toolCalls': getattr(message, 'tool_calls', None), 'toolCallId': getattr(message, 'tool_call_id', None)})
                if getattr(message, 'type', '') == 'human' and normalize_content(message.content) == q.query_text:
                    break
            transcript.reverse()
            for sender, text in [('user', q.query_text), ('agent', reply)]:
                mid = q.id + ':' + sender
                if text and not session.get(AgentMessage, mid):
                    session.add(AgentMessage(id=mid, session_id=q.session_id, sender=sender, role=sender,
                        text=text, created_at=q.created_at if sender == 'user' else datetime.now(timezone.utc),
                        tool_trace={'events': state.get('trace') or [], 'messages': transcript} if sender == 'agent' else None, message_metadata={'queryId': q.id, 'clientMessageId': q.client_message_id,
                            'records': records if sender == 'agent' else [], 'showAllDetails': q.response['showAllDetails'] if sender == 'agent' else False,
                            'pendingAction': q.response.get('pendingAction') if sender == 'agent' else None}))


def save_turn(state, client_message_id=None):
    _persist(state)


def save_paused_turn(state, client_message_id=None):
    _persist(state, paused=True)


def save_llm_failure(session_id, query_id, text, client_message_id=None):
    if not query_id:
        return
    with session_scope() as session:
        q = session.get(Query, query_id)
        if q:
            q.status, q.decision = 'llm_unavailable', 'LLM_UNAVAILABLE'
            mid = q.id + ':user'
            if not session.get(AgentMessage, mid):
                session.add(AgentMessage(id=mid, session_id=session_id, sender='user', role='user', text=text,
                    message_metadata={'queryId': q.id, 'clientMessageId': client_message_id}))


def save_event_turn(session_id, job_id, query_id, reply_text):
    # Event processing persists its own Query, message, snapshot and acknowledgement.
    return None
