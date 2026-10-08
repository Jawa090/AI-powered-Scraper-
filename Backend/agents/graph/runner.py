"""Serialized conversation turns, immutable retries and durable job notifications."""
from __future__ import annotations
import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Literal
import psycopg
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import select
from Database.controller import session_scope
from Database.models.query import Query
from Database.models.session import AgentSession
from Database.models.session_event import SessionEvent
from Database.models.message import AgentMessage
from agents.graph.graph import get_compiled_graph
from agents.graph.persist import save_llm_failure, save_paused_turn, save_turn
from agents.graph.utils import normalize_content
from agents.llm.chat_model import LLMUnavailable, get_chat_model, invoke_llm, invoke_structured
from settings import settings

logger = logging.getLogger(__name__)


class ConfirmationDecision(BaseModel):
    decision: Literal['approve', 'reject', 'modify', 'unrelated']
    edits: dict[str, Any] | None = None
    text: str


@contextmanager
def session_lock(session_id: str, timeout_s: float = 30):
    conn = psycopg.connect(settings.CHECKPOINT_DB_URL, autocommit=True)
    acquired = False
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            acquired = bool(conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', (session_id,)).fetchone()[0])
            if acquired:
                break
            time.sleep(.1)
        if not acquired:
            raise HTTPException(409, 'Session is busy with another request.')
        yield
    finally:
        if acquired:
            conn.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (session_id,))
        conn.close()


_get_lock = session_lock


def pending_interrupt(graph, config):
    return bool(graph.get_state(config).interrupts)


def classify_confirmation(text, pending):
    prompt = ('Classify the reply to this exact scrape proposal as approve/reject/modify/unrelated. '
        'Only approve explicit consent to the unchanged proposal. For changes return edits as a JSON object '
        'using category, city, us_state, quantity, record_kind, has_email, has_phone, source. '
        'A reduced quantity or changed location is modify and requires another search and approval. '
        f'Proposal: {json.dumps(pending)}\nReply: {text}')
    result = invoke_structured(ConfirmationDecision, [HumanMessage(content=prompt)])
    return ConfirmationDecision.model_validate(result.model_dump() if isinstance(result, BaseModel) else result).model_dump()


def to_api_response(out, state_snapshot, query_id=None):
    state = getattr(state_snapshot, 'values', state_snapshot) or out or {}
    qid = query_id or state.get('query_id')
    with session_scope() as db:
        q = db.get(Query, qid) if qid else None
        if q and q.response:
            return dict(q.response)
    raise RuntimeError('A durable response is required before returning a successful turn')


def run_turn(user, session_id, text, client_message_id=None, new_only=False, expected_proposal_id=None):
    uid = user.id
    with session_lock('user:' + uid):
        with session_scope() as db:
            sess = db.get(AgentSession, session_id)
            if not sess:
                active = db.scalar(select(AgentSession).where(AgentSession.user_id == uid, AgentSession.status == 'active'))
                if active:
                    raise HTTPException(409, 'Start or restore your active conversation first.')
                db.add(AgentSession(id=session_id, user_id=uid, department_id=user.department_id or 'dept-default',
                    agent_id='agent-master', status='active'))
            elif sess.user_id != uid:
                raise HTTPException(403, 'Session does not belong to you.')
            elif sess.status != 'active':
                raise HTTPException(409, {'code': 'SESSION_CLOSED'})
    graph = get_compiled_graph()
    config = {'configurable': {'thread_id': session_id}, 'recursion_limit': settings.RECURSION_LIMIT}
    with session_lock(session_id):
        with session_scope() as db:
            from services.sessions import require_active
            require_active(session_id, db)
            prior = db.scalar(select(Query).where(Query.session_id == session_id,
                Query.client_message_id == client_message_id)) if client_message_id else None
            if prior and prior.response:
                return dict(prior.response)
            snap = graph.get_state(config)
            if expected_proposal_id is not None:
                pending = snap.interrupts[0].value if snap.interrupts else {}
                actual_id = (pending.get('proposal') or {}).get('tool_call_id')
                if actual_id != expected_proposal_id:
                    raise HTTPException(409, 'This scrape proposal has changed. Reload the conversation and review it again.')
            qid = prior.id if prior else str(uuid.uuid4())
            if not prior:
                db.add(Query(id=qid, user_id=uid, session_id=session_id, query_text=text,
                    client_message_id=client_message_id, status='received', parameters={}))
            from datetime import datetime, timezone
            db.get(AgentSession, session_id).updated_at = datetime.now(timezone.utc)
        try:
            if prior and snap.next and snap.values.get('query_id') == qid and not snap.interrupts:
                out = graph.invoke(None, config)
            elif snap.interrupts:
                from agents.graph.nodes.rag_retrieve import rag_retrieve
                pending = snap.interrupts[0].value
                decision = classify_confirmation(text, pending)
                current = {**snap.values, 'user_text': text, 'messages': [HumanMessage(content=text)], 'trace': []}
                interpreted = {}
                if decision['decision'] in ('modify', 'unrelated'):
                    from agents.graph.nodes.gather_requirements import interpret_request
                    interpreted = interpret_request(current)
                kb = rag_retrieve({**current, **interpreted})
                changes = {'query_id': qid, 'client_message_id': client_message_id, 'user_text': text, **interpreted, **kb}
                if decision['decision'] in ('modify', 'unrelated'):
                    changes.update(turn_id=str(uuid.uuid4()), served_lead_ids=[], tool_steps=0)
                else:
                    changes['last_search'] = {**(snap.values.get('last_search') or {}), 'items': [], 'lead_ids': []}
                    changes['served_lead_ids'] = []
                with session_scope() as db:
                    q = db.get(Query, qid)
                    q.parameters = {'kind': 'confirmation', 'originatingQueryId': (pending.get('proposal') or {}).get('query_id')}
                graph.update_state(config, changes)
                out = graph.invoke(Command(resume=decision), config)
            else:
                repairs = []
                for call in getattr((snap.values.get('messages') or [None])[-1], 'tool_calls', []) or []:
                    repairs.append(ToolMessage(content='Previous turn superseded.', tool_call_id=call['id']))
                out = graph.invoke({'messages': [*repairs, HumanMessage(content=text)], 'user_id': uid,
                    'user_role': user.role, 'department_id': user.department_id, 'session_id': session_id,
                    'query_id': qid, 'turn_id': str(uuid.uuid4()), 'client_message_id': client_message_id,
                    'user_text': text, 'new_only': new_only, 'event_job_id': None, 'served_lead_ids': []}, config)
            after = graph.get_state(config)
            if after.interrupts:
                save_paused_turn(after.values)
            else:
                save_turn(after.values)
            return to_api_response(out, after, qid)
        except LLMUnavailable as exc:
            save_llm_failure(session_id, qid, text, client_message_id)
            raise HTTPException(503, exc.to_dict()) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception('chat_turn_failed', extra={'query_id': qid, 'session_id': session_id})
            with session_scope() as db:
                db.get(Query, qid).status = 'failed'
            raise HTTPException(500, {'error': {'code': 'INTERNAL_ERROR',
                'message': 'The request could not be completed.'}}) from exc


def run_event_turn(session_id, job_id):
    """Deliver one durable completion; an AI failure leaves the event pending."""
    from datetime import datetime, timezone
    from Database.models.job import Job
    from services.delivery import delivery_rows, record_delivery
    with session_lock(session_id):
        with session_scope() as db:
            event = db.scalar(select(SessionEvent).where(SessionEvent.session_id == session_id,
                SessionEvent.job_id == job_id).order_by((SessionEvent.status == 'pending').desc(), SessionEvent.created_at).with_for_update())
            if not event:
                return {'pending': True}
            closed_session = db.get(AgentSession, session_id)
            if closed_session and closed_session.status == 'cleared' and event.status == 'delivered':
                return {'suppressed': True, 'alreadyDelivered': True}
            if event.status == 'delivered':
                return {'alreadyDelivered': True, 'queryId': event.query_id}
            q = db.get(Query, event.query_id)
            job = db.get(Job, job_id)
            sess = db.get(AgentSession, session_id)
            if sess and sess.status == 'cleared':
                from services.completion import log_cleared_collection
                from services.delivery import recovered_job_records
                recovered = recovered_job_records(db, job)
                q.parameters = {**(q.parameters or {}), 'chatCleared': True, 'requestFulfilled': False,
                    'collectionCancelled': True, 'deliveryKind': 'recovered', 'recoveredRecords': len(recovered), 'timeoutOptions': None}
                log_cleared_collection(db, q, event, recovered, job)
                return q.response
            records = delivery_rows(db, q.id)
            initial = (q.parameters or {}).get('initialRecordsDelivered', 0)
            outcome = {key: (q.parameters or {}).get(key) for key in (
                'requestFulfilled', 'deliveryKind', 'matchingRecordsDelivered', 'requestedRecords',
                'recoveredRecords', 'understoodRequest', 'collectionCancelled', 'timedOut', 'timeoutOptions')}
            matching_count = outcome['matchingRecordsDelivered']
            if matching_count is None:  # Older pending events contained only matching rows.
                matching_count = len(records)
            facts = {'status': job.status, 'recordsFound': job.records_found,
                'recordsDelivered': len(records), 'requested': (q.parameters or {}).get('slots', {}).get('quantity'),
                **outcome, 'initialRecordsDelivered': initial, 'requestTotalDelivered': initial + matching_count,
                'error': job.error_message, 'records': records}
            try:
                timeout_instruction = (' If timedOut is true, explain that the scraper was stopped after five minutes without records. '
                    'Ask whether the user wants to rerun it or try another compatible scraper. Give a short description of every '
                    'source in timeoutOptions. Identify recommendedSource as the most likely compatible alternative based on '
                    'record type and coverage, without promising results. If it is null, explain that there is no other '
                    'compatible source; bid scrapers cannot supply contractor companies.') if outcome.get('timedOut') else ''
                answer = invoke_llm(get_chat_model(), [SystemMessage(content='Report the completed scrape using only supplied facts. When requestFulfilled is false, explicitly say the requested requirements were not met and the displayed rows are the data recovered, which may differ in category, location or contact availability. Never describe recovered rows as matching, verified fulfillment. Explain the understoodRequest and matching count against the requested count. All recovered rows were saved with deduplication. When fulfilled, only requested matching rows are displayed. Explain source errors separately. Use concise, natural language for the user; do not expose internal field names, JSON values, identifiers or code terminology. The displayed table supplies the individual rows. Do not execute new work. Recovery choices require fresh user approval.'),
                    HumanMessage(content=json.dumps(facts) + timeout_instruction)])
                from agents.graph.nodes.finalize import grounded_reply
                answer = grounded_reply(get_chat_model(), [HumanMessage(content=json.dumps(facts))], facts, answer)
            except LLMUnavailable as exc:
                if not outcome.get('timedOut'):
                    raise HTTPException(503, exc.to_dict()) from exc
                from services.recovery_options import timeout_reply
                from langchain_core.messages import AIMessage
                answer = AIMessage(content=timeout_reply(facts))
            reply = normalize_content(answer.content)
            if not reply.strip():
                raise HTTPException(503, {'error': {'code': 'LLM_UNAVAILABLE', 'message': 'Empty completion response'}})
            record_delivery(db, q, records)
            q.status = 'completed'
            q.response = {'reply': reply, 'records': records, 'total': len(records), 'queryId': q.id,
                'showAllDetails': outcome['deliveryKind'] == 'recovered' or bool((q.parameters or {}).get('slots', {}).get('show_all_details')),
                'jobId': job.id, 'sessionId': session_id, 'status': job.status, 'decision': q.decision,
                **outcome, 'initialRecordsDelivered': initial, 'requestTotalDelivered': initial + matching_count}
            db.add(AgentMessage(id=q.id + ':agent', session_id=session_id, sender='agent', role='agent',
                text=reply, message_metadata={'queryId': q.id, 'jobId': job.id, 'records': records,
                                             **outcome, 'showAllDetails': q.response['showAllDetails'], 'event': True}))
            event.status, event.reply, event.delivered_at = 'delivered', reply, datetime.now(timezone.utc)
            db.flush()
            more = db.scalar(select(SessionEvent.id).where(SessionEvent.session_id == session_id,
                SessionEvent.job_id == job_id, SessionEvent.status == 'pending').limit(1))
            return {**q.response, 'morePending': bool(more)}
